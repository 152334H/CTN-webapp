#!/bin/bash
echo Checking for GPU...
if [ "$CTN_MODE" = 'CPU' ]
then
	sed -i 's/cuda:0/cpu/;s/CPU_PITCH = False/CPU_PITCH = True/' /talknet/controllable_talknet.py
	sed -i 's/\.cuda()//' /talknet/hifi-gan/denoiser.py
	echo 'CPU mode on.'
else
	echo 'GPU assumed to be present!'
fi

# TODO: replace this with a toml config file (or similar)
if [ "$PRELOAD_MODELS" != 'true' ]
then sed -i 's/PRELOAD_MODELS = True/PRELOAD_MODELS = False/' /talknet/controllable_talknet.py
fi
if [ -n "$MODEL_CACHE_SIZE" ]
then sed -i "s/MODEL_CACHE_SIZE = 4/MODEL_CACHE_SIZE = $MODEL_CACHE_SIZE/" /talknet/controllable_talknet.py
fi

echo Personal stuff...
[ -f /talknet/personal.sh ] && /talknet/personal.sh

echo Launching TalkNet...
case "$SERVER_TYPE" in 
	'uwsgi') uwsgi --ini uwsgi.ini;;
	'debug') python3.8 app.py;;
	*) echo 'unknown server type provided; crashing!'; exit 1;;
esac

