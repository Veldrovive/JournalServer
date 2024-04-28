from jserver.storage import ResourceManager

def test_uploaded_text_file(rmanager: ResourceManager, session_test_text_file_id):
    with rmanager.get_temp_local_file(session_test_text_file_id) as file_path:
        with open(file_path, "r") as f:
            assert f.read() == "Hello World!"
