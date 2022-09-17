window.onload = () => {


const generate_button = document.querySelector('button[name=gen-button]')
const upload_audio = document.querySelector('input[name=upload-audio]')
const upload_audio_button = document.getElementById('upload-audio-button')
const uploaded_audio = document.getElementById('uploaded-audio')
const semitones = document.querySelector('input[name=pitch-factor]')
const model_dropdown = document.getElementById('model-dropdown')
const audio_sourcing = document.getElementById('audio-sourcing')
const audio_debugging = document.getElementById('audio-debugging')
const debug_audio_player = document.getElementById('debug-audio')
const debug_audio_src = document.getElementById('debug-audio-src')
const debug_audio_button = document.getElementById('debug-audio-button')

async function build_model_list() {
	const res = await fetch('/static/model_list.json');
	const json = await res.json();
	json.forEach(d => {
		const opt = document.createElement('option');
		opt.value = opt.innerHTML = d.title;
		opt.disabled = d.disabled;
		model_dropdown.appendChild(opt)
	})
}
build_model_list().then(() => console.log('loaded model list'))

const checkbox = {};
["pf", "pc", "dra", "srec"].forEach(id => {
	checkbox[id] = document.querySelector(`input[name=cbox-${id}]`);
})

checkbox.dra.addEventListener("change", () => {
	debug_audio_player.style.visibility = uploaded_audio.style.visibility = audio_sourcing.style.visibility =
		(checkbox.pc.disabled = checkbox.dra.checked) ?
		'hidden' : 'visible';
	generate_button.disabled = !checkbox.dra.checked && uploaded_audio.style.visibility === 'hidden';
});
checkbox.pf.addEventListener("change", () => {
	semitones.disabled = !checkbox.pf.checked;
});


function tempSpinner(needsSpinner, promise) {
	const spinner = document.createElement('div')
	spinner.className = 'spinner'
	spinner.id = 'temp-spinner'
	old_inner = needsSpinner.innerHTML;
	needsSpinner.innerHTML = "";
	needsSpinner.appendChild(spinner);
	needsSpinner.disabled = true;
	return promise.finally(res => {
		needsSpinner.removeChild(spinner);
		needsSpinner.innerHTML = old_inner;
		needsSpinner.disabled = false;
		return res;
	})
}


var audio_id = '';
async function submit_audio(f) {
	const fdata = new FormData();
	fdata.append('file', f);
	try {
		const res = await fetch('/api/upload_audio', {
			method: 'POST',
			body: fdata
		});
		const json = await res.json();
		return json.audio_id;
	} catch (e) {
		replace_info(`${e}`, true)
	}
}

upload_audio_button.addEventListener('click', () =>
	upload_audio.click()
);
upload_audio.addEventListener('change', e => {
	let fname = '';
	if (upload_audio.files) {
		fname = e.target.value.split('\\').pop();
		const label = upload_audio.nextElementSibling;
		if (fname.match(/\.wav$/)) {
			label.innerHTML = fname;
			uploaded_audio.style.visibility = 'visible'
			uploaded_audio.firstElementChild.src = URL.createObjectURL(e.target.files[0]);
			tempSpinner(upload_audio_button, submit_audio(e.target.files[0]))
				.then(res => {
					audio_id = res;
					uploaded_audio.load();
					audio_debugging.style.display = 'flex';
				});
		} else {
			label.innerHTML = "ONLY .wav files accepted";
			uploaded_audio.style.visibility = 'hidden'
	  	audio_debugging.style.display = 'none';
			audio_id = ''
		}
		generate_button.disabled = uploaded_audio.style.visibility === 'hidden';
	}
});
debug_audio_button.addEventListener('click', () => {
	if (!audio_id) 
		replace_info("Bug: Couldn't find audio ID", true)
	else {
		tempSpinner(debug_audio_button, (async () => {
			const res = await fetch(`/api/debug_audio/${audio_id}`);
			if (res.status != 200) {
				const json = await res.json();
				throw json.error;
			}
			return res.text();
		})()).then(audio_src => {
			debug_audio_src.src = audio_src;
			debug_audio_player.style.visibility = 'visible'
			debug_audio_player.load();
		}).catch(err => replace_info(err, true))
	}
})



const info_element = document.getElementById('generated-info')
function replace_info(s, error=false) {
	info_element.innerHTML = s;
	info_element.style.color = error ? 'red' : 'inherit';
}

const output_audio = document.getElementById('audio-out')
generate_button.addEventListener('click', () => {
	const text = document.getElementById('transcript-input').value.trim();
	if (!/^[ -~]+$/.test(text)) {
		return replace_info('Transcript is empty or contains invalid characters.', true);
	}

	const req = {
		transcript: text,
		pitch_options: {
			pf: checkbox.pf.checked,
			pc: checkbox.pc.checked,
			dra: checkbox.dra.checked,
			srec: checkbox.srec.checked,
			pitch_factor: semitones.value || 0
		},
		model: model_dropdown.value,
		audio_id,
	}
	tempSpinner(generate_button, (async () => {
		const res = await fetch('/api/submit', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(req),
		})
		const json = await res.json();
		if (res.status != 200) throw json.error;
		return json;
	})()).then(json => {
			replace_info(json.msg)
			output_audio.style.visibility = 'visible'
			output_audio.firstElementChild.src = json.audio;
			output_audio.load()
	}).catch(err => 
			replace_info(err, true)
	);
	return replace_info('')
})



// modal
function model_content(title, body_id) {
	const modal_body = document.getElementById(body_id);
	modal_body.hidden = false;
	document.body.removeChild(modal_body);
	//
	const content = document.createElement('div');
	content.className = "modal-content"
	//
	const header = document.createElement('div');
	header.className = "modal-header"
	const h5 = document.createElement('h5');
	h5.className = "modal-title";
	h5.innerHTML = title;
	header.appendChild(h5);
	//
	const body = document.createElement('div');
	body.className = "modal-body";
	body.appendChild(modal_body);
	//
	const footer = document.createElement('div');
	footer.className = "modal-footer"
	const button = document.createElement('button');
	button.id = "close"
	button.className = "ml-auto btn btn-secondary";
	button.innerHTML = 'Close'
	button.onclick = () => modal_disable(body_id);
	footer.appendChild(button);
	//
	content.appendChild(header);
	content.appendChild(body);
	content.appendChild(footer);
	return content;
}
function modal_enable(title, body_id) {
	const root = document.createElement('div')
	root.id = 'modal-root'
	root.tabIndex = -1
	root.style = "position: relative; z-index: 1050; display: block;"
	//
	const first = document.createElement('div');
	first.className = "modal fade show";
	first.style = "display: block;";
	first.onclick = () => modal_disable(body_id);
	first.setAttribute('role', 'dialog');
	first.role = "dialog";
	first.tabIndex = -1;
	//
	const inner = document.createElement('div');
	inner.onclick = e => e.stopPropagation();
	inner.id = "modal";
	inner.setAttribute('role', 'document');
	inner.className = "modal-dialog";
	//inner.style = "display: block;"
	//inner.tabIndex = -1;
	inner.appendChild(model_content(title, body_id));
	//
	first.appendChild(inner);
	const second = document.createElement('div');
	second.className = "modal-backdrop fade show"
	//
	const preroot = document.createElement('div')
	preroot.className = "";
	preroot.appendChild(first);
	preroot.appendChild(second);
	root.append(preroot)
	//
	document.body.appendChild(root);
}
function modal_disable(body_id) {
	console.log('attempting close')
	const modal_body = document.getElementById(body_id);
	modal_body.hidden = true;
	const root = document.getElementById('modal-root')
	document.body.removeChild(root);
	document.body.appendChild(modal_body);
}

const license_info_link = document.getElementById('open-license');
license_info_link.addEventListener('click', () => {
	modal_enable('About', 'modal-body-about')
});
const tips_link = document.getElementById('open-tips');
tips_link.addEventListener('click', () => {
	modal_enable('Tips', 'modal-body-tips')
});

};
