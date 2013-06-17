from setuptools import setup, find_packages

setup(
    name = "escrotum",
    version = "0.1.0",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    entry_points = {
        'console_scripts': [
            'escrotum = escrotum.main:run',
        ],
    }
)

