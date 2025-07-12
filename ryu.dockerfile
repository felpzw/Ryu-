FROM python:3.8-slim-bullseye
WORKDIR /code
RUN apt update -y && pip install wheel "setuptools<58" "eventlet==0.30.2" && pip install ryu
EXPOSE 6633 6653 6640
ENTRYPOINT ["ryu-manager"]
