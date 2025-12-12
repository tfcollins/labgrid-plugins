def test_kuiper_dl(target):
    kuiper = target.get_driver("KuiperDLDriver")
    kuiper.download_release()

    kuiper.get_boot_files_from_release()
