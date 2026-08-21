import glob
import os
import subprocess


class FilesystemRetirementGateway:
    def revoke_client(self, revoke_script: str, instance_name: str) -> bool:
        if not os.access(revoke_script, os.X_OK):
            return False

        subprocess.run(
            [revoke_script, instance_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True

    def delete_file(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True

    def delete_directory(self, path: str) -> bool:
        if not os.path.isdir(path):
            return False

        import shutil

        shutil.rmtree(path)
        return True

    def delete_files_with_prefix(self, directory: str, prefix: str) -> list[str]:
        if not os.path.exists(directory):
            return []

        deleted = []
        pattern = os.path.join(directory, f"{prefix}*")
        for file_path in glob.glob(pattern):
            if os.path.isfile(file_path):
                os.remove(file_path)
                deleted.append(file_path)
        return deleted
