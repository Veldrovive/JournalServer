

# Creation of a new input handler
1. Create the handler script in `/jserver/input_handlers/handler_types`
    1. This should be a subclass of InputHandler
    2. Add the input handler class to the list in `/jserver/input_handlers/handler_types/__init__.py`
2. Create the handler config in `/jserver/config/input_handler_config` with a new unique `handler_type`
    1. This is the type of the config parameter to the input handler
    2. Add the config to the list of configs in `/jserver/config/input_handler_config/__init__.py`

# Creation of a new entry type
Remember to add the type for deletion.
1. Create a new entry file in `/jserver/entries/types`
    1. Entries must be subclasses of `EntryABC`
    2. Define the functions `entry_uuid`, `entry_hash`, `construct_output_data`
        * The `entry_uuid` field can be tricky. Its primary purpose is to check if two entries are the same for deduplication. Telling if two arbitraries are the same is often impossible so it needs to be approximated by using indicators like the start time of the entry and the entry data.
        * `construct_output_data` is mostly just for converting the `data` field into a serializable form. For entries that contain files you also must convert the file id into a presigned url so that the frontend can access the file.
2. Create a new EntryType enum string in `/jserver/entries/primitives.py` with a unique id
3. Add the new entry to the list in `/jserver/entries/__init__.py`
4. Add a deletion handler in `/jserver/storage/entry_manager.py`
