import json
import os


def test_kuiper_dl(target):
    kuiper = target.get_driver("KuiperDLDriver")
    kuiper.download_release()

    # Verify img file exists
    path = kuiper.kuiper_resource.cache_path
    cache_file = os.path.join(path, kuiper.cache_datafile)
    assert os.path.isfile(cache_file)

    # Load json cache_file
    with open(cache_file) as f:
        data = json.load(f)

    release_path = data[kuiper.kuiper_resource.release_version]["image_path"]
    assert os.path.isfile(release_path)

    files = kuiper.get_boot_files_from_release()

    for file in files:
        assert os.path.isfile(file)
