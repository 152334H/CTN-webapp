ARG APP_IMAGE=ubuntu:20.04
FROM ${APP_IMAGE}
ARG CTN_MODE=CPU
ENV CTN_MODE=$CTN_MODE
RUN mkdir /talknet
RUN touch /talknet/is_docker

ENV TZ=Etc/GMT
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update && apt-get install -y git ffmpeg python3.8 python3-pip curl
COPY ./ControllableTalkNet/requirements.txt /talknet
RUN python3.8 -m pip --no-cache-dir install -r "/talknet/requirements.txt" -f https://download.pytorch.org/whl/torch_stable.html
COPY ./NeMo /talknet/NeMo
RUN python3.8 -m pip --no-cache-dir install /talknet/NeMo
RUN python3.8 -m pip uninstall -y pesq
RUN python3.8 -m pip install pesq==0.0.2
RUN python3.8 -m pip install werkzeug==2.0.3
RUN python3.8 -m pip install uwsgi marshmallow
#echo Updating typing_extensions as a hotfix for https://github.com/pydantic/pydantic/issues/442
RUN python3.8 -m pip --quiet install -U typing_extensions

COPY ./hifi-gan/ /talknet/hifi-gan 
COPY ./ControllableTalkNet /talknet
COPY ./model_lists_extra /talknet/model_lists
COPY ./app /talknet
COPY ./docker_launch.sh /talknet

WORKDIR /talknet
ENV FLASK_ENV production
#EXPOSE 9191

RUN chmod +x /talknet/docker_launch.sh
CMD ["./docker_launch.sh"]
