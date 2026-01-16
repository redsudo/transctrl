import sys
import os
import time

# Add client to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../")

from client.transctrl_client import TransmissionControllerClient

def main():
    socket_path = os.getenv("SOCKET_PATH", "/tmp/transctrl.sock")
    client = TransmissionControllerClient(socket_path)

    print("--- Reconciling ---")
    # Note: These paths must exist on your host and be under ALLOWED_MOUNT_BASE
    # For a quick test, you might need to create them or adjust the values.
    try:
        result = client.reconcile([
            {
                "id": "test-instance",
                "config_path": "/mnt/configs/test",
                "data_path": "/mnt/data/test",
                "watch_path": "/mnt/watch/test",
                "web_port": 19091,
                "data_port": 15141
            }
        ])
        print(f"Result: created={result.created_count}, destroyed={result.destroyed_count}, errors={result.errors}")
    except Exception as e:
        print(f"Reconcile failed: {e}")

    print("\n--- Getting Status ---")
    status = client.get_status()
    for inst in status:
        print(f"ID: {inst.id}, Status: {inst.status}, Container: {inst.container_id}")

if __name__ == "__main__":
    main()
