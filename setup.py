from setuptools import setup, find_packages

setup(
    name="dwlab_cmkapi",
    version="0.06.01",
    packages=find_packages(),
    scripts=[],
    install_requires=["dwlab_basicpy>=0.06.01", "requests>=2.22.0", "urllib3>=1.25.10"],
)
