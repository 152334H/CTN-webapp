#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
die() {
	echo "$1"
	exit 1
}
[ "$SCRIPT_DIR" == "$(pwd)" ] || die "Run this script at the root of this repository ($SCRIPT_DIR)"

echo 'Stopping existing servers (if any)...'
docker stop talknet-webapp && docker rm talknet-webapp

# TODO: replace this with `git submodule foreach git pull`, or similar.
echo Updating submodules...
#git -C ...
git -C ./NeMo pull origin main -q || die "could not update NeMo"
#git -C /talknet reset --hard origin/main -q
git -C ./ControllableTalkNet pull origin main -q || die "could not update TalkNet"
#git -C /talknet/hifi-gan reset --hard origin/master -q
git -C ./hifi-gan pull origin master -q || die "Could not update HiFi-GAN"

echo 'Attempting to minify JS/CSS...'
if command -v uglifyjs
then uglifyjs -c -m -o app/static/index.js -- app/static/index.src.js
else cp app/static/index.src.js app/static/index.js
fi
if command -v uglifycss
then uglifycss --output app/static/index.css app/static/index.src.css
else cp app/static/index.src.css app/static/index.css
fi

DEVICE=${DEVICE:-CPU}
case "$DEVICE" in
	GPU | gpu | cuda | CUDA) echo 'Using GPU'
		docker build -t talknet-webapp --build-arg APP_IMAGE=nvidia/cuda:11.0.3-base-ubuntu20.04 --build-arg CTN_MODE="GPU" .;;
	CPU | cpu) echo 'Using CPU'
		docker build -t talknet-webapp .;;
	*) die "ERROR: DEVICE=$DEVICE is not a valid option."
esac

# TODO: use docker-compose instead.
docker run "$@" \
	-e "SERVER_TYPE=${SERVER_TYPE:-debug}" \
	-e "PRELOAD_MODELS=${PRELOAD_MODELS:-false}" \
	-e "MODEL_CACHE_SIZE=${MODEL_CACHE_SIZE:-4}" \
	--restart unless-stopped -d -p "${PORT:-8050}:8050" \
	-v talknet-model-cache:/talknet/models \
	-h talknet-webapp --name=talknet-webapp talknet-webapp
