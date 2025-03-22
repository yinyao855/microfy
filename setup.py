import setuptools

curr_version = ""

# package_data = {
#     "microfy": [
#         "VERSION",
#         "requirements.txt",
#         "src/microfy/*"
#     ]
# }


def get_version():
    global curr_version
    with open('VERSION') as f:
        version_str = f.read()
    curr_version = version_str


def upload():
    with open("README.md", "r") as fh:
        long_description = fh.read()
    with open('requirements.txt') as f:
        required = f.read().splitlines()

    setuptools.setup(
        name="microfy",
        version=curr_version,
        author="yinyao855",
        author_email="1311095683@qq.com",
        description="Automate Your Monolith to Microservices Migration",  # 库描述
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://pypi.org/project/microfy/",  # 库的官方地址
        packages=setuptools.find_packages(where="src"),
        package_dir={"": "src"},
        include_package_data=True,
        classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
        ],
        python_requires='>=3.6',
        install_requires=required,
    )


def main():
    try:
        get_version()
        upload()
        print("Upload success , Current VERSION:", curr_version)
    except Exception as e:
        raise Exception("Upload package error", e)


if __name__ == '__main__':
    main()
