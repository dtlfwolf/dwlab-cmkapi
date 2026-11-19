"""Versioned vendor adapter for stopped-site temporary skeletons, not services."""

import os
from pathlib import Path
import pwd
import re
import sys


class NativeRuntimeRunner:
    """Use Checkmk's own runtime layout under the verified site OS identity."""

    def prepare(self, site: str) -> None:
        """Create temporary skeleton files without starting or resetting the site."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", site):
            raise ValueError("Invalid site")
        account = pwd.getpwnam(site)
        if (os.geteuid(), os.getegid()) != (account.pw_uid, account.pw_gid):
            raise ValueError("Real site OS identity required")
        from cmk.ccc import version
        from cmk.ccc.site import omd_site
        import omdlib
        from omdlib.contexts import SiteContext
        from omdlib.main import read_site_config
        from omdlib.tmpfs import prepare_and_populate_tmpfs
        from omdlib.version_info import VersionInfo

        if site != omd_site() or not version.__version__.startswith(("2.4.", "2.5.")):
            raise ValueError("Unsupported native context")
        context = SiteContext(site)
        context.set_config(read_site_config(str(Path("/omd/sites") / site)))
        if context.conf["TMPFS"] != "off" or not context.is_stopped(False):
            raise ValueError("Stopped disk-backed runtime required")
        skeleton = f"/omd/versions/{omdlib.__version__}/skel"
        if version.__version__.startswith("2.4."):
            prepare_and_populate_tmpfs(VersionInfo(), context, skeleton)
        else:
            prepare_and_populate_tmpfs(
                context.conf, VersionInfo(), site, str(Path("/omd/sites") / site),
                context.tmp_dir, context.replacements(), context.skel_permissions, skeleton,
            )


if __name__ == "__main__":
    NativeRuntimeRunner().prepare(sys.argv[1])
