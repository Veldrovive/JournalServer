import time
from datetime import datetime, timedelta
import base64
import requests
import tempfile
import xml.etree.ElementTree
from tcxreader.tcxreader import TCXReader, TCXExercise
from pydantic import ValidationError

from jserver.config.input_handler_config import FitbitAPIHandlerConfig
from jserver.input_handlers.input_handler import InputHandler, EntryInsertionLog
from jserver.entries import FitbitActivityEntry, GeolocationEntry
from jserver.entries.types.personal_sensor_entries import Geolocation

from jserver.shared_models.fitbit_api import *
from jserver.exceptions import *

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import Callable

SCOPE = ['activity', 'heartrate', 'location', 'nutrition', 'profile', 'settings', 'sleep', 'social', 'weight']

class FitbitAuth:
    """

    """
    def __init__(self, key_collection, client_id, client_secret):
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.collection = key_collection

        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = None

        self.auth_url = "https://www.fitbit.com/oauth2/authorize"
        self.token_url = "https://api.fitbit.com/oauth2/token"

        self.remaining_requests = -1
        self.seconds_till_reset = -1

    def get_authorization_url(self, redirect_uri):
        self.redirect_uri = redirect_uri
        return f"{self.auth_url}?response_type=code&client_id={self.client_id}&scope={'+'.join(SCOPE)}&redirect_uri={redirect_uri}"

    def make_request(self, url, method="GET", params=None, data=None, headers=None):
        """
        Makes a request to the given URL with the given method and parameters.
        """
        logger.info(f"Making request to {url}")
        if self.access_token is None:
            raise FitbitUnauthorizedException("No access token. User must authenticate.")
        for retry_ind in range(2):  # Retry once after re-authenticating
            if headers is None:
                headers = {}
            headers['Authorization'] = f"Bearer {self.access_token}"
            response = requests.request(method, url, params=params, data=data, headers=headers)
            # The headers contains a `Fitbit-Rate-Limit-Limit`, `Fitbit-Rate-Limit-Remaining`, `Fitbit-Rate-Limit-Reset`
            # We extract those
            try:
                rate_limit = {
                    "limit": response.headers.get("Fitbit-Rate-Limit-Limit"),
                    "remaining": response.headers.get("Fitbit-Rate-Limit-Remaining"),
                    "reset": response.headers.get("Fitbit-Rate-Limit-Reset"),
                }
                self.remaining_requests = int(rate_limit["remaining"])
                self.seconds_till_reset = int(rate_limit["reset"])
                logger.info(f"Rate Limit: {rate_limit}")
                if rate_limit["remaining"] == '0':
                    raise ToManyRequestsException()  # Should not be caught
                return response
            except TypeError:
                logger.error(f"Error getting rate limit: {response.headers}")
                res_json = response.json()
                logger.error(f"Response: {res_json}")
                # Attempt to re-auth
                authorized = self.attempt_auth()
                if not authorized:
                    raise FitbitUnauthorizedException("Failed to re-authenticate user.")
                # Otherwise we should be good to retry
                continue
        raise Exception("Failed to make request")


    def check_token(self):
        """
        Returns true if the token is valid
        """
        if self.access_token is None:
            return False
        if self.refresh_token is None:
            return False
        if self.expires_at < time.time():
            return False
        return True

    def save_tokens(self):
        """
        Saves the tokens into the mongo database
        """
        # Remove the previous tokens
        self.collection.delete_many({})
        self.collection.insert_one({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        })

    def recall_tokens(self):
        """
        Gets the previous tokens from the mongo database
        """
        tokens = self.collection.find_one()
        if tokens is None:
            return None, None, -1
        return tokens["access_token"], tokens["refresh_token"], tokens["expires_at"]

    def check_auth(self) -> bool:
        """
        Sends a request to `https://api.fitbit.com/1/user/-/profile.json` to attempt to get the current user's profile
        """
        try:
            response = self.make_request("https://api.fitbit.com/1/user/-/profile.json")
            if response.status_code == 200:
                return True
            else:
                res_json = response.json()
                logger.error(f"Failed to authenticate user. Got response: {res_json}")
                return False
        except FitbitUnauthorizedException as e:
            logger.error(f"Failed to authenticate user. Got unauthorized exception: {e}")
            return False

    def attempt_auth(self):
        """
        Attempts to authenticate the user
        """
        logger.info('Attempting to authenticate FitBit user')
        access_token, refresh_token, expires_at = self.recall_tokens()

        # Check if the access token is still valid
        if expires_at > time.time():
            logger.info('Token is still valid')
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.expires_at = expires_at
            if self.check_auth():
                logger.info('User is authenticated')
                return True
            else:
                logger.info('Token was valid, but user is not authenticated. Attempting to refresh token.')
            # If this fails, we can still fall back to trying to refresh the token
        else:
            logger.info('Token has expired. Attempting to refresh token.')

        # Attempt to refresh the token
        logger.info('Refreshing token...')
        if self.refresh_token is not None:
            refreshed = self.req_refresh_token()
            if refreshed:
                logger.info(f"Token refreshed. New token expires at {self.expires_at}.")
                if self.check_auth():
                    logger.info('User is authenticated')
                    return True
                else:
                    logger.info('Failed to authenticate user after refreshing token. There is something wrong with the token. User must re-authenticate.')
            else:
                logger.info('Failed to refresh token. User must re-authenticate.')

        # If the refresh token is invalid, then the user must re-authenticate
        logger.info('User must re-authenticate.')
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        return False

    def req_refresh_token(self):
        """
        Refreshes the token
        """
        logger.info('Refreshing token...')
        body = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'expires_in': 28800,
        }

        # Generate the base64 encoded string
        client_id_secret = f'{self.client_id}:{self.client_secret}'
        client_id_secret_bytes = client_id_secret.encode('ascii')
        client_id_secret_base64 = base64.b64encode(client_id_secret_bytes)
        client_id_secret_base64_str = client_id_secret_base64.decode('ascii')

        headers = {
            "Authorization": f"Basic {client_id_secret_base64_str}"
        }

        response = requests.post(self.token_url, data=body, headers=headers)
        res_json = response.json()

        try:
            access_token = res_json['access_token']
            refresh_token = res_json['refresh_token']
            expires_in = res_json['expires_in']

            self.access_token = access_token
            self.refresh_token = refresh_token
            self.expires_at = time.time() + expires_in
            return True
        except KeyError:
            logger.info('Failed to refresh token')
            return False

    def request_token(self, auth_code):
        """
        Sends a post request to the token URL with a body that contains
        client_id: The Fitbit API application ID from https://dev.fitbit.com/apps.
        code: The authorization code
        grant_type: authorization_code

        with Authorization: Basic BASE64_ENCODED(CLIENT_ID:CLIENT_SECRET)
        """
        body = {
            'client_id': self.client_id,
            'code': auth_code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri,
        }

        # Generate the base64 encoded string
        client_id_secret = f'{self.client_id}:{self.client_secret}'
        client_id_secret_bytes = client_id_secret.encode('ascii')
        client_id_secret_base64 = base64.b64encode(client_id_secret_bytes)
        client_id_secret_base64_str = client_id_secret_base64.decode('ascii')

        headers = {
            "Authorization": f"Basic {client_id_secret_base64_str}"
        }

        res_json = None
        try:
            response = requests.post(self.token_url, data=body, headers=headers)
            res_json = response.json()
            access_token = res_json['access_token']
            refresh_token = res_json['refresh_token']
            expires_in = res_json['expires_in']
            expires_at = time.time() + expires_in

            logger.info(f"Got token: {access_token}, {refresh_token}, {expires_at}")
            return access_token, refresh_token, expires_at
        except KeyError:
            logger.error(f"Error getting token: {res_json}")
            return None, None, None

    def set_auth_code(self, auth_code):
        """
        Attempts to authorize with the given code
        """
        access_token, refresh_token, expires_at = self.request_token(auth_code)
        if access_token is not None:
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.expires_at = expires_at
            self.save_tokens()
            res = self.attempt_auth()
            return res
        return False

class FitbitAPI:
    def __init__(self, authenticator: FitbitAuth):
        self.authenticator = authenticator

    def get_profile(self):
        response = self.authenticator.make_request("https://api.fitbit.com/1/user/-/profile.json")
        return response.json()["user"]

    def get_full_activity_log(self, start_date: datetime | None = None) -> list[Activity]:
        """
        Gets the full activity log for the user following the pagination links
        """
        full_activity_log = []
        # Start at 2000
        if start_date is None:
            start_date = datetime.fromisoformat("2000-01-01")
        start_date_str = start_date.strftime("%Y-%m-%d")
        current_url = f"https://api.fitbit.com/1/user/-/activities/list.json?afterDate={start_date_str}&sort=asc&limit=100&offset=0"
        while current_url is not None:
            response = self.authenticator.make_request(current_url)
            json = response.json()
            if "activities" not in json:
                print(json)
                raise Exception(f"Error getting activities: {json}")
            for activity in json["activities"]:
                try:
                    activity = Activity.model_validate(activity)
                except ValidationError as e:
                    # Log the entire json and re-raise the exception
                    logger.error(f"Error validating activity: {activity}")
                    raise e

                full_activity_log.append(activity)
            pagination = Pagination.model_validate(json["pagination"])
            current_url = pagination.next
            if len(current_url) == 0:
                current_url = None
        return full_activity_log

    def read_activity_tcx(self, activity: Activity) -> str:
        """
        Reads the TCX file for the given activity
        """
        response = self.authenticator.make_request(activity.tcxLink)
        return response.text

    def get_activity_details(self, activity: Activity) -> DetailedActivity:
        """
        Parses the TCX file
        """
        tcx = self.read_activity_tcx(activity)
        reader = TCXReader()
        with tempfile.NamedTemporaryFile() as temp:
            temp.write(tcx.encode('utf-8'))
            temp.seek(0)
            data: TCXExercise = reader.read(temp.name)
        # The data in data is just attributes. We will extract these as a dictionary
        trackpoints = [trackpoint.__dict__ for trackpoint in data.trackpoints]
        tcx_data = data.__dict__
        tcx_data['trackpoints'] = trackpoints
        activity_details = TCXActivity.model_validate(tcx_data)

        return DetailedActivity(
            activity=activity,
            activityTCXData=activity_details,
        )


class FitbitAPIInputHandler(InputHandler):
    _requires_db_connection = True
    _takes_file_input = False
    _requires_input_folder = False

    def __init__(self, handler_id: str, config: FitbitAPIHandlerConfig, on_entries_inserted: Callable[[list[EntryInsertionLog]], None], db_connection = None):
        super().__init__(handler_id, config, on_entries_inserted, db_connection)

        self.geolocation_downsample_period_s = config.geolocation_downsample_period_s
        self.start_date = config.start_date

        self.ready = False
        self.set_up_database()

        self.auth = FitbitAuth(self.key_store_collection, config.client_id, config.client_secret)
        self.api = FitbitAPI(self.auth)
        try:
            authorized = self.auth.attempt_auth()
            logger.info(f"Authorized: {authorized}")
            if authorized:
                self.profile = self.api.get_profile()
            else:
                self.profile = None
        except ToManyRequestsException as e:
            logger.error(f"Too many requests: {e}")
            self.profile = None


        self.ready = True

    @property
    def _rpc_map(self):
        return {
            "set_auth_code": self.set_auth_code,
            "get_auth_url": self.get_auth_url,
        }

    def get_state(self):
        """
        Gets the state of the input handler
        """
        return {
            "rate_limited": self.auth.remaining_requests == 0,
            "remaining_requests": self.auth.remaining_requests,
            "seconds_till_reset": self.auth.seconds_till_reset,
            "authorized": self.auth.check_token(),
            "profile": self.profile,
        }

    def set_up_database(self):
        self.activity_collection = self.db_connection.get_collection("fitbit_activities")
        self.key_store_collection = self.db_connection.get_collection("fitbit_key_store")

        self.activity_collection.create_index("log_id", unique=True)

    def set_auth_code(self, body):
        """
        Sets the authorization code
        """
        auth_code = body['auth_code']
        res = self.auth.set_auth_code(auth_code)
        if res:
            self.profile = self.api.get_profile()
        else:
            self.profile = None
        return {"success": res}

    def get_auth_url(self, body: dict):
        """
        Gets the authorization URL
        """
        return {"url": self.auth.get_authorization_url(body['redirect_uri'])}

    def set_activity_processed(self, activity: Activity):
        """
        Adds the activity to the database so we know it has been processed
        """
        save_dict = {
            "log_id": activity.logId,
        }
        self.activity_collection.insert_one(save_dict)

    def check_activity_processed(self, activity: Activity) -> bool:
        """
        Checks if the activity has already been processed
        """
        return self.activity_collection.find_one({"log_id": activity.logId}) is not None

    def process_activity_to_entry(self, activity: Activity) -> tuple[FitbitActivityEntry, list[GeolocationEntry]]:
        """
        Processes a single activity to a set of entries

        In order to get the downsampled geolocation entries, we partition in the trackpoints into minute intervals
        For each of these intervals we take the average of the latitude, longitude, and altitude
        """
        if activity.tcxLink is None:
            logger.error(f"No TCX link for activity {activity.logId}")
            return None, []
        activity_details = self.api.get_activity_details(activity)
        location = None
        if len(activity_details.activityTCXData.trackpoints) > 0:
            location = (activity_details.activityTCXData.trackpoints[0].latitude, activity_details.activityTCXData.trackpoints[0].longitude)
        start_time = datetime.fromisoformat(activity.originalStartTime)
        end_time = start_time + timedelta(milliseconds=activity.activeDuration)
        activity_entry = FitbitActivityEntry(
            data = activity,
            start_time = int(round(start_time.timestamp() * 1000)),
            end_time = int(round(end_time.timestamp() * 1000)),
            latitude = location[0] if location is not None else None,
            longitude = location[1] if location is not None else None,
            group_id = str(activity.logId),
            seq_id = 0,
            input_handler_id = self.handler_id,
        )
        geolocation_entries = []
        trackpoints = activity_details.activityTCXData.trackpoints
        if len(trackpoints) == 0:
            return activity_entry, geolocation_entries

        def process_partition(partition: list[TCXTrackPointLocal], order_index: int):
            if len(partition) == 0:
                return
            latitude = sum([trackpoint.latitude for trackpoint in partition]) / len(partition)
            longitude = sum([trackpoint.longitude for trackpoint in partition]) / len(partition)
            start_time = partition[0].time
            end_time = partition[-1].time
            location = Geolocation(
                latitude=latitude,
                longitude=longitude,
                altitude=None,
            )
            geolocation_entry = GeolocationEntry(
                data = location,
                start_time = int(round(start_time.timestamp() * 1000)),
                end_time = int(round(end_time.timestamp() * 1000)),
                latitude = latitude,
                longitude = longitude,
                group_id = str(activity.logId),
                seq_id = order_index + 1,
                input_handler_id = self.handler_id,
            )
            geolocation_entries.append(geolocation_entry)

        start_time = trackpoints[0].time
        current_partition = []
        order_index = 0
        for trackpoint in trackpoints:
            if trackpoint.time - start_time > timedelta(seconds=self.geolocation_downsample_period_s):
                # We have reached the end of the partition
                process_partition(current_partition, order_index)
                current_partition = []
                start_time = trackpoint.time
            current_partition.append(trackpoint)
        process_partition(current_partition, order_index)

        return activity_entry, geolocation_entries

    def get_activity_entries(self) -> tuple[list[FitbitActivityEntry], list[GeolocationEntry]]:
        """
        Parses the fitbit activity files to get a set of activities and a downsampled set of geolocation entries
        """
        try:
            activities = self.api.get_full_activity_log(self.start_date)
        except ToManyRequestsException as e:
            logger.error(f"Too many requests: {e}")
            return [], []
        except FitbitUnauthorizedException as e:
            logger.error(f"Unauthorized: {e}")
            return [], []

        activity_entries = []
        geolocation_entries = []
        for activity in activities:
            if self.check_activity_processed(activity):
                logger.info(f"Skipping activity {activity.logId}")
                continue
            logger.info(f"Processing activity {activity.logId}")
            try:
                activity_entry, geolocation_entry = self.process_activity_to_entry(activity)
                if activity_entry is None:
                    logger.error(f"Error processing activity {activity.logId}")
                    continue
                activity_entries.append(activity_entry)
                geolocation_entries.extend(geolocation_entry)
                self.set_activity_processed(activity)
            except xml.etree.ElementTree.ParseError as e:
                logger.error(f"Error parsing activity {activity.logId}: {e}")
            except ToManyRequestsException as e:
                logger.error(f"Too many requests: {e}")
                break
            except FitbitUnauthorizedException as e:
                logger.error(f"Unauthorized: {e}")
                break

        return activity_entries, geolocation_entries

    def trigger(self, entry_insertion_log: list[EntryInsertionLog] = []):
        """
        Triggers the input handler
        """
        logger.warning("Triggering Fitbit API input handler")
        logger.info(f"Start Date: {self.start_date}")
        activity_entries, geolocation_entries = self.get_activity_entries()
        logger.info(f"Got {len(activity_entries)} activity entries and {len(geolocation_entries)} geolocation entries")
        for entry in activity_entries:
            self.insert_entry(entry_insertion_log, entry)
        for entry in geolocation_entries:
            self.insert_entry(entry_insertion_log, entry)

    async def _on_trigger_request(self, entry_insertion_log: list[EntryInsertionLog], file: str | None = None, metadata: dict[str, str] | None = None):
        """
        Called when a request is received on POST /input_handlers/{handler_id}/request_trigger
        """
        self.trigger(entry_insertion_log)

    async def _on_trigger_new_file(self, entry_insertion_log: list[EntryInsertionLog], file: str):
        """
        Called when a new file is added to the input handler directory
        """
        pass

    async def _on_trigger_interval(self, entry_insertion_log: list[EntryInsertionLog]):
        """
        Called when the interval is reached
        """
        self.trigger(entry_insertion_log)


