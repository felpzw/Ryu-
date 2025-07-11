FROM python:3.8-slim-bullseye

RUN apt update -y && pip install wheel "setuptools<58" "eventlet==0.30.2" && pip install ryu
EXPOSE 6633
CMD ["ryu-manager", "ryu.app.simple_switch"]
