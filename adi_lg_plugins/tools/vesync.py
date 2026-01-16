from pyvesync import VeSync


def check_for_outlets(username, password):
    """Check if VeSync outlets are available for the given account."""
    # Create a new VeSync object
    manager = VeSync(username=username, password=password)

    # To enable debugging
    manager.debug = True

    # Login to the VeSync account
    manager.login()

    # Check if logged in
    assert manager.enabled

    # Get devices
    manager.get_devices()

    # Update all devices
    manager.update()

    # OR Iterate through devices and update individually
    # for device in manager.outlets:
    #     device.update()
    
    # Return the list of outlets
    return manager.outlets


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Check for VeSync outlets associated with the given account."
    )
    parser.add_argument(
        "--username", required=True, help="VeSync account username (email)"
    )
    parser.add_argument(
        "--password", required=True, help="VeSync account password"
    )

    args = parser.parse_args()
    try:
        outlets = check_for_outlets(args.username, args.password)
        print("Found VeSync outlets:")
        for outlet in outlets:
            print(f" - {outlet}")
    except Exception as e:
        print(f"Error: {e}")