from setuptools import setup, find_packages

setup(
    name="dwlab_cmkapi",
    version="0.6.1",
    packages=find_packages(),
    scripts=[],
    install_requires=["dwlab-basicpy>=0.6.1", "requests>=2.22.0", "urllib3>=1.25.10"],
)
