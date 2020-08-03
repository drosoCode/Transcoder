FROM jrottenberg/ffmpeg:4.1-nvidia1804

ENTRYPOINT []

WORKDIR /home/server
COPY ./requirements.txt ./requirements.txt
#COPY . .

ENV LD_LIBRARY_PATH=  
RUN apt-get update && apt-get install -y python3 python3-pip libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev
ENV LD_LIBRARY_PATH="/usr/local/lib:/usr/local/lib64:/usr/lib:/usr/lib64:/lib:/lib64"

RUN pip3 install --no-cache-dir -r requirements.txt


RUN apt-get update && apt-get install -y locales && locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

#CMD "./start.sh"
CMD "bash"
