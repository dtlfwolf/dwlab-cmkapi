# dwlabcmkapi

`dwlabcmkapi` provides a simple and extensible Python interface to interact with Checkmk servers, manage monitoring configurations, schedule backups, and integrate Checkmk operations into your custom workflows.

## ✨ Features

- Connect to and authenticate with Checkmk servers
- Automate host and service management
- Schedule and execute backup jobs
- Integrate with existing Python systems or automation pipelines
- Modular design for easy extension

## 📦 Installation

Install the package and its dependencies with pip:

```bash
pip install dwlabcmkapi

For local development in this workspace:

```bash
python3 -m pip install -e ../dwlabbasicpy
python3 -m pip install -e ../dwlabbackup
python3 -m pip install -e .
```

## 🧱 Packaging

`dwlabcmkapi` uses a standard `src/` layout and is built with setuptools:

```bash
python3 -m build --no-isolation
```

The package ships its logging configuration from `src/dwlabcmkapi/etc/logging.yaml`.

## 🧪 Development

For local test runs inside the DW-Lab workspace:

```bash
python3 -m pytest
```

The root `conftest.py` adds the local `src/` tree and sibling package `src/` directories to `sys.path`, matching the editable workspace setup.
