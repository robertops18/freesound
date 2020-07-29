var sound = "https://freesound.org" + document.getElementById("waveform").getAttribute("sound_url");
var wavesurfer = createWavesurfer(sound);


var zoomValueInit = 0
var zoomValue = 0
var zoomRatio = 10

var AudioContext = window.AudioContext || window.webkitAudioContext;

document.body.onkeyup = function(event) {
    keyUp(event);
}
document.body.onkeydown = function(event) {
    if (event.keyCode == 32 || event.keyCode == 39 || event.keyCode == 37) {
        return false;
    } else {
        keyDown(event);
    }
};

var sound_name = document.getElementById("waveform").getAttribute("sound_name");
var sound_id = document.getElementById("waveform").getAttribute("sound_id");
var username = document.getElementById("waveform").getAttribute("username");

// Query Selectors
initQuerySelectors();

// Wavesurfer events
initWavesurferEvents();

//Filters and effects knob
var lowpass_knob = createKnob('lowpass_knob', 0, 20000, 'Hz', true);
var bandpass_freq_knob = createKnob('bandpass_freq_knob', 0, 20000, 'Hz', true);
var bandpass_q_knob = createKnob('bandpass_q_knob', 0, 100, 'Q', true,1);
var highpass_knob = createKnob('highpass_knob', 0, 20000, 'Hz', true);

var amplify_knob = createKnob('amplify_knob', -20, 20, 'dB', true, 0);
var fade_in_knob = createKnob('fade_in_knob', 0, 10, 'In (s)', false);
var fade_out_knob = createKnob('fade_out_knob', 0, 10, 'Out (s)', false);
var rate_knob = createKnob('rate_knob', 0.2, 3, '', true, 1);

initKnobListeners();

// Undo and redo data structures
var undoArray = []
var redoArray = []

// Array of applied filters for undo and redo
var appliedFilters = []

// Initialization functions 
function initQuerySelectors() {
    document.querySelector('#zoom_in').onclick = function () {
        zoomIn();
    }
    document.querySelector('#zoom_out').onclick = function () {
        zoomOut();
    }
    document.querySelector('#get_selection_btn').onclick = function () {
        toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: 'Undo Get Selected Region', tooltipTextRedo: 'Redo Get Selected Region'});
        getSelectedRegion();
    }
    document.querySelector('#undo_get_selection_btn').onclick = function () {
        toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: 'Undo Get Original Sample', tooltipTextRedo: 'Redo Get Original Sample'});
        getOriginalSample(sound);
    }
    /*
    document.querySelector('#reset_filters').onclick = function () {
        resetFilters();
    }

     */
    document.querySelector('#delete_region').onclick = function () {
        toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: 'Undo Delete Region', tooltipTextRedo: 'Redo Delete Region'});
        deleteRegion();
    }
    document.querySelector('#empty_region').onclick = function () {
        toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: 'Undo Clear Region', tooltipTextRedo: 'Redo Clear Region'});
        emptyRegion();
    }
    document.querySelector('#reverse').onclick = function () {
        toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: 'Undo Reverse', tooltipTextRedo: 'Redo Reverse'});
        reverse();
    }
    document.querySelector('#export').onclick = function () {
        exportBufferToFile();
    }
    document.querySelector('#play_btn').onclick = function () {
        playPause();
    }
    document.querySelector('#undo').onclick = function () {
        undo();
    }
    document.querySelector('#redo').onclick = function () {
        redo();
    }
}

function initWavesurferEvents() {
    // Reset region when clicking the waveform
    wavesurfer.on('seek', function(region) {
        wavesurfer.clearRegions();
        setDisabledWhenNoRegion(true);
        seekingPos = ~~(wavesurfer.backend.getPlayedPercents() * wavesurfer.backend.buffer.length);
    });

    // Delete previous region when creating a new one
    wavesurfer.on('region-created', function() {
        deletePreviousRegion();
    });

    wavesurfer.on('ready', function() {
        zoomValueInit = 900 / wavesurfer.getDuration();
        zoomValue = zoomValueInit

        var st = new window.soundtouch.SoundTouch(
            wavesurfer.backend.ac.sampleRate
        );
        var buffer = wavesurfer.backend.buffer;
        var channels = buffer.numberOfChannels;
        var l = buffer.getChannelData(0);
        var r = channels > 1 ? buffer.getChannelData(1) : l;
        var length = buffer.length;
        var seekingPos = null;
        var seekingDiff = 0;

        var source = {
            extract: function(target, numFrames, position) {
                if (seekingPos != null) {
                    seekingDiff = seekingPos - position;
                    seekingPos = null;
                }

                position += seekingDiff;

                for (var i = 0; i < numFrames; i++) {
                    target[i * 2] = l[i + position];
                    target[i * 2 + 1] = r[i + position];
                }

                return Math.min(numFrames, length - position);
            }
        };

        var soundtouchNode;

        wavesurfer.on('play', function() {
            seekingPos = ~~(wavesurfer.backend.getPlayedPercents() * length);
            st.tempo = wavesurfer.getPlaybackRate();
            if (st.tempo === 1) {
                wavesurfer.backend.disconnectFilters();
            } else {
                if (!soundtouchNode) {
                    var filter = new window.soundtouch.SimpleFilter(source, st);
                    soundtouchNode = window.soundtouch.getWebAudioNode(
                        wavesurfer.backend.ac,
                        filter
                    );
                }
                wavesurfer.backend.setFilter(soundtouchNode);
            }
        })
        wavesurfer.on('finish', function() {
            soundtouchNode && soundtouchNode.disconnect();
        });

        wavesurfer.on('pause', function() {
            soundtouchNode && soundtouchNode.disconnect();
        });
    })
}

function initKnobListeners() {
    var lowpassFilter, highpassFilter, bandpassFilterFreq, bandpassFilterQ;
    var changeListenerLowpass = function(knob, value, mouseUp) {
        if (value !== 0) {
            if (mouseUp) {
                toUndo('filter', {
                    filterType: 'lowpass',
                    frequency: value,
                    Q: 1,
                    tooltipTextUndo: 'Undo Lowpass filter',
                    tooltipTextRedo: 'Redo Lowpass filter'
                });
                applyFilter('lowpass', value, 1);
            } else {
                if (lowpassFilter) {
                    lowpassFilter.frequency.value = value;
                } else {
                    lowpassFilter = applyFilter('lowpass', value, 1, true);
                }
            }
        }
    }
    lowpass_knob.addListener(changeListenerLowpass);

    var changeListenerHighpass = function(knob, value, mouseUp) {
        if (value !== 0) {
            if (mouseUp) {
                toUndo('filter', {
                    filterType: 'highpass',
                    frequency: value,
                    Q: 1,
                    tooltipTextUndo: 'Undo Highpass filter',
                    tooltipTextRedo: 'Redo Highpass filter'
                });
                applyFilter('highpass', value, 1);
            } else {
                if (highpassFilter) {
                    highpassFilter.frequency.value = value;
                } else {
                    highpassFilter = applyFilter('highpass', value, 1, true);
                }
            }
        }
    }
    highpass_knob.addListener(changeListenerHighpass);

    var changeListenerBandpassFreq = function(knob, value, mouseUp) {
        if (value !== 0) {
            if (mouseUp) {
                toUndo('filter', {
                    filterType: 'bandpass',
                    frequency: value,
                    Q: bandpass_q_knob.getValue(),
                    tooltipTextUndo: 'Undo Bandpass filter Freq',
                    tooltipTextRedo: 'Redo Bandpass filter Freq'
                });
                applyFilter('bandpass', value, bandpass_q_knob.getValue());
            } else {
                if (bandpassFilterFreq) {
                    bandpassFilterFreq.frequency.value = value;
                } else {
                    bandpassFilterFreq = applyFilter('bandpass', value, bandpass_q_knob.getValue(), true);
                }
            }
        }
    }
    bandpass_freq_knob.addListener(changeListenerBandpassFreq);

    var changeListenerBandpassQ = function(knob, value, mouseUp) {
        if (bandpass_freq_knob.getValue() > 0) {
            if (mouseUp) {
                toUndo('filter', {
                    filterType: 'bandpass',
                    frequency: bandpass_freq_knob.getValue(),
                    Q: value,
                    tooltipTextUndo: 'Undo Bandpass filter Q',
                    tooltipTextRedo: 'Redo Bandpass filter Q'
                });
                applyFilter('bandpass', bandpass_freq_knob.getValue(), value);
            } else {
                if (bandpassFilterQ) {
                    bandpassFilterQ.Q.value = value;
                } else {
                    bandpassFilterQ = applyFilter('bandpass', bandpass_freq_knob.getValue(), value, true);
                }
            }
        }
    }
    bandpass_q_knob.addListener(changeListenerBandpassQ);

    var changeListenerAmplify = function(knob, value, mouseUp) {
        if (mouseUp) {
            //TODO: Undo and redo amplify
        }
        amplify(value);
    }
    amplify_knob.addListener(changeListenerAmplify);

    var changeListenerFadeIn = function(knob, value, mouseUp) {
        if (mouseUp) {
            //TODO: Undo and redo fadein
        }
        fadeIn(value);
    }
    fade_in_knob.addListener(changeListenerFadeIn);

    var changeListenerFadeOut = function(knob, value, mouseUp) {
        if (mouseUp) {
            //TODO: Undo and redo fadeout
        }
        fadeOut(value);
    }
    fade_out_knob.addListener(changeListenerFadeOut);

    var changeListenerPlaybackRate = function(knob, value, mouseUp) {
        if (mouseUp) {
            //TODO: Undo and redo playback rate
        }
        changePlaybackRate(value);
    }
    rate_knob.addListener(changeListenerPlaybackRate);
}

function createWavesurfer(song) {
    var wavesurfer = WaveSurfer.create({
        container: '#waveform',
        waveColor: '#f5a52c',
        progressColor: '#b36d04',
        cursorColor: '#FFFFFF',
        backgroundColor: '#111212',
        cursorWidth: 1,
        height: 200,
        plugins: [
            WaveSurfer.cursor.create({
              showTime: true,
              opacity: 1,
              customShowTimeStyle: {
                'background-color': '#000',
                color: '#fff',
                padding: '2px',
                'font-size': '10px'
              }
            }),
            WaveSurfer.regions.create({drag:false, color: 'rgba(256, 256, 256, 1)'}),
            WaveSurfer.timeline.create({
                container: '#wave-timeline'
            })
        ]
    });
    wavesurfer.enableDragSelection({drag:false, color: 'rgba(256, 256, 256, 0.3)'});
    wavesurfer.load(song);

    return wavesurfer;
}

function playPause() {
    wavesurfer.playPause();
}

function zoomIn() {
    zoomValue += zoomRatio
    wavesurfer.zoom(zoomValue);
}

function zoomOut() {
    if (zoomValue > zoomValueInit) {
        zoomValue -= zoomRatio
        wavesurfer.zoom(zoomValue);
    }
}

// Print aux function
function print(s) {
    console.log(s);
}

// Undo and redo actions

function undo() {
    if (undoArray.length > 0) {
        var undoAction = undoArray.pop();
        document.querySelector('#undo').disabled = undoArray.length === 0;
        if (undoArray.length === 0) {
            $('#undo_tooltip').tooltip().attr('data-original-title', 'Undo');
        } else {
            $('#undo_tooltip').tooltip().attr('data-original-title', undoArray[undoArray.length - 1].action.tooltipTextUndo);
        }
        switch (undoAction.type) {
            case 'buffer':
                toRedo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: undoAction.action.tooltipTextUndo, tooltipTextRedo: undoAction.action.tooltipTextRedo});
                var previousBuffer = undoAction.action.buffer;
                wavesurfer.empty()
                wavesurfer.loadDecodedBuffer(previousBuffer);
                break;
            case 'filter': // TODO: Undo functions with filters
                toRedo('filter', undoAction.action);
                // 1. Pop filter from array
                appliedFilters.pop()
                // 2. Cancel its behaviour or apply previous one
                if (appliedFilters.length > 0) {
                    var lastFilter = appliedFilters[appliedFilters.length - 1]
                    applyFilter(lastFilter.filterType, lastFilter.frequency, lastFilter.Q, true);
                } else {
                    cancelFilter()
                }
                break;
        }
    } else {
        print('Nothing to undo')
    }
}

function redo() {
    if (redoArray.length > 0) {
        var redoAction = redoArray.pop();
        document.querySelector('#redo').disabled = redoArray.length === 0;
        if (redoArray.length === 0) {
            $('#redo_tooltip').tooltip().attr('data-original-title', 'Redo');
        } else {
            $('#redo_tooltip').tooltip().attr('data-original-title', redoArray[redoArray.length - 1].action.tooltipTextRedo);
        }
        switch (redoAction.type) {
            case 'buffer':
                toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: redoAction.action.tooltipTextUndo, tooltipTextRedo: redoAction.action.tooltipTextRedo});
                var previousBuffer = redoAction.action.buffer;
                wavesurfer.empty()
                wavesurfer.loadDecodedBuffer(previousBuffer);
                break;
            case 'filter':
                toUndo('filter', redoAction.action);
                // Apply filter
                applyFilter(redoAction.action.filterType, redoAction.action.frequency, redoAction.action.Q);
                break;
        }
    } else {
        print('Nothing to redo')
    }
}

function toUndo(type, action) {
    var undoAction = {
        type: type,
        action: action
    }
    undoArray.push(undoAction);
    document.querySelector('#undo').disabled = undoArray.length === 0;
    document.querySelector('#undo').style.pointerEvents = undoArray.length === 0 ? 'none' : 'auto';
    $('#undo_tooltip').tooltip().attr('data-original-title', action.tooltipTextUndo);
}

function toRedo(type, action) {
    var redoAction = {
        type: type,
        action: action
    }
    redoArray.push(redoAction);
    document.querySelector('#redo').disabled = redoArray.length === 0;
    document.querySelector('#redo').style.pointerEvents = redoArray.length === 0 ? 'none' : 'auto';
    $('#redo_tooltip').tooltip().attr('data-original-title', action.tooltipTextRedo);
}

// Buffer related functions
function createBuffer(originalBuffer, duration) {
    var sampleRate = originalBuffer.sampleRate
    var frameCount = duration * sampleRate
    var channels = originalBuffer.numberOfChannels 
    return new AudioContext().createBuffer(channels, frameCount, sampleRate)
  }
  
function copyBuffer(fromBuffer, fromStart, fromEnd, toBuffer, toStart) {
    var sampleRate = fromBuffer.sampleRate
    var frameCount = (fromEnd - fromStart) * sampleRate
    for (var i = 0; i < fromBuffer.numberOfChannels; i++) {
        var fromChanData = fromBuffer.getChannelData(i)
        var toChanData = toBuffer.getChannelData(i)
        for (var j = 0, f = Math.round(fromStart*sampleRate), t = Math.round(toStart*sampleRate); j < frameCount; j++, f++, t++) {
            toChanData[t] = fromChanData[f]
        }
    }
}

function concatBuffer(buffer1, buffer2) {
	var context = new AudioContext();
    var numberOfChannels = Math.min( buffer1.numberOfChannels, buffer2.numberOfChannels );
    var tmp = context.createBuffer( numberOfChannels, (buffer1.length + buffer2.length), buffer1.sampleRate );
    for (var i=0; i<numberOfChannels; i++) {
      var channel = tmp.getChannelData(i);
      channel.set( buffer1.getChannelData(i), 0);
      channel.set( buffer2.getChannelData(i), buffer1.length);
    }
    return tmp;
}

function exportBufferToFile() {
    var blob = encodeWAV(wavesurfer.backend.buffer);

    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    document.body.appendChild(a);
    a.style = "display: none";
    a.href = url;
    var sound = sound_id + '__' + username + '__' + sound_name + '__EDIT.wav';
    a.download = sound;
    a.click();
    window.URL.revokeObjectURL(url);
}

function writeUTFBytes(view, offset, string) {
    for (var i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

function encodeWAV(originalBuffer){
    var channelData = originalBuffer.getChannelData(0);
    var buffer = new ArrayBuffer(44 + channelData.length * 2);
    var view = new DataView(buffer);
    var sampleRate = originalBuffer.sampleRate / 2;
  
    // RIFF chunk descriptor
    writeUTFBytes(view, 0, 'RIFF');
    view.setUint32(4, 44 + channelData.length * 2, true);
    writeUTFBytes(view, 8, 'WAVE');

    // FMT sub-chunk
    writeUTFBytes(view, 12, 'fmt ');
    view.setUint32(16, 16, true); // chunkSize
    view.setUint16(20, 1, true); // wFormatTag
    view.setUint16(22, 2, true); // wChannels: stereo (2 channels)
    view.setUint32(24, sampleRate, true); // dwSamplesPerSec
    view.setUint32(28, sampleRate * 4, true); // dwAvgBytesPerSec
    view.setUint16(32, 4, true); // wBlockAlign
    view.setUint16(34, 16, true); // wBitsPerSample

    // data sub-chunk
    writeUTFBytes(view, 36, 'data');
    view.setUint32(40, channelData.length * 2, true);

    // write the PCM samples
    var index = 44;
    var volume = 1;
    for (var i = 0; i < channelData.length; i++) {
        view.setInt16(index, channelData[i] * (0x7FFF * volume), true);
        index += 2;
    }

    // our final blob
    var blob = new Blob([view], { type: 'audio/wav' });
  
    return blob;
  }

function reverse() {
    var buffer = wavesurfer.backend.buffer;
    Array.prototype.reverse.call( buffer.getChannelData(0) );
    if (buffer.numberOfChannels > 1) {
        Array.prototype.reverse.call( buffer.getChannelData(1) );
    }
    wavesurfer.empty();
    wavesurfer.loadDecodedBuffer(buffer);
}

// Gain related functions

function fadeIn(duration) { //TODO
    var gainNode = wavesurfer.backend.gainNode;
    gainNode.gain.cancelScheduledValues( wavesurfer.backend.ac.currentTime );
    gainNode.gain.setValueAtTime( 0.00001, wavesurfer.backend.ac.currentTime );
    gainNode.gain.exponentialRampToValueAtTime( 1.0, wavesurfer.backend.ac.currentTime + duration );
}

function fadeOut(duration) {
    var gainNode = wavesurfer.backend.gainNode;
    var sm = getSmoothFade(wavesurfer.backend.ac, gainNode, {type: 'exponential'});
    sm.fadeOut();
}

function amplify(value) {
    wavesurfer.backend.gainNode.gain.value = Math.pow(10, (value / 20));
    /*
    wavesurfer.params.barHeight = value;
    wavesurfer.empty();
    wavesurfer.loadDecodedBuffer(wavesurfer.backend.buffer);

     */
}

// Region related functions
function getSelectedRegion() {
    var regionsList = wavesurfer.regions.list;
    for (var r in regionsList) {
        var region = regionsList[r];
        var start = region.start;
        var end = region.end;
        var duration = end - start;
        var buffer = createBuffer(wavesurfer.backend.buffer, duration)
        // copy
        copyBuffer(wavesurfer.backend.buffer, start, end, buffer, 0)

        // load the new buffer
        wavesurfer.empty()
        wavesurfer.loadDecodedBuffer(buffer)
    }
    wavesurfer.clearRegions();
    setDisabledWhenNoRegion(true);
}

function getOriginalSample(song) {
    wavesurfer.clearRegions();
    wavesurfer.empty()
    wavesurfer.load(song);
    setDisabledWhenNoRegion(true);
}

function deletePreviousRegion() {
    setDisabledWhenNoRegion(false);
    var regionList = wavesurfer.regions.list;
    if (Object.keys(regionList).length > 0) {
        var firstRegionID = Object.keys(regionList)[0];
        regionList[firstRegionID].remove();
    }
}

function deleteRegion() {
    setDisabledWhenNoRegion(true);
	var regionList = wavesurfer.regions.list;
	var region = regionList[Object.keys(regionList)[0]]

	var startTime = region.start;
    var endTime = region.end;

    var totalDuration = wavesurfer.getDuration();
    var firstBuffer;
    var secondBuffer;
    var finalBuffer;

    // Case 1: All the sample is selected
    if (startTime == 0 && endTime == totalDuration) {
        resetAndLoadNewBuffer();
    }
    // Case 2: Region is at the start of the sample
    else if (startTime == 0) {
        finalBuffer = createBuffer(wavesurfer.backend.buffer, totalDuration - endTime);
        copyBuffer(wavesurfer.backend.buffer, endTime, totalDuration, finalBuffer, 0);

        resetAndLoadNewBuffer(finalBuffer);
    }
    // Case 3: Region is at the end of the sample
    else if (endTime == totalDuration) {
        finalBuffer = createBuffer(wavesurfer.backend.buffer, startTime);
        copyBuffer(wavesurfer.backend.buffer, 0, startTime, finalBuffer, 0);

        resetAndLoadNewBuffer(finalBuffer);
    }
    // Case 4: Region is in the middle
    else {
        firstBuffer = createBuffer(wavesurfer.backend.buffer, startTime);
        copyBuffer(wavesurfer.backend.buffer, 0, startTime, firstBuffer, 0);

        secondBuffer = createBuffer(wavesurfer.backend.buffer, totalDuration - endTime);
        copyBuffer(wavesurfer.backend.buffer, endTime, totalDuration, secondBuffer, 0);

        finalBuffer = concatBuffer(firstBuffer, secondBuffer);

        resetAndLoadNewBuffer(finalBuffer);
    }
}

function resetAndLoadNewBuffer(finalBuffer = null) {
    wavesurfer.clearRegions();
    wavesurfer.empty();
    if (finalBuffer) {
        wavesurfer.loadDecodedBuffer(finalBuffer);
    } else {
        var emptyBuffer = createBuffer(wavesurfer.backend.buffer, wavesurfer.getDuration());
        wavesurfer.loadDecodedBuffer(emptyBuffer);
    }
}

function emptyRegion() {
    setDisabledWhenNoRegion(true);
    var regionList = wavesurfer.regions.list;
	var region = regionList[Object.keys(regionList)[0]]
	
	var startTime = region.start;
    var endTime = region.end;

    var totalDuration = wavesurfer.getDuration();
    var firstBuffer;
    var secondBuffer;
    var emptyBuffer;
    var finalBuffer;

    // Case 1: All the sample is selected
    if (startTime == 0 && endTime == totalDuration) {
        resetAndLoadNewBuffer();
    }
    // Case 2: Region is at the start of the sample
    else if (startTime == 0) {
        emptyBuffer = createBuffer(wavesurfer.backend.buffer, endTime);
        
        secondBuffer = createBuffer(wavesurfer.backend.buffer, totalDuration - endTime);
        copyBuffer(wavesurfer.backend.buffer, endTime, totalDuration, secondBuffer, 0);

        finalBuffer = concatBuffer(emptyBuffer, secondBuffer);

        resetAndLoadNewBuffer(finalBuffer);
    }
    // Case 3: Region is at the end of the sample 
    else if (endTime == totalDuration) {
        firstBuffer = createBuffer(wavesurfer.backend.buffer, startTime);
        copyBuffer(wavesurfer.backend.buffer, 0, startTime, firstBuffer, 0);

        emptyBuffer = createBuffer(wavesurfer.backend.buffer, endTime - startTime);

        finalBuffer = concatBuffer(firstBuffer, emptyBuffer);

        resetAndLoadNewBuffer(finalBuffer);
    }     
    // Case 4: Region is in the middle
    else {
        firstBuffer = createBuffer(wavesurfer.backend.buffer, startTime);
        copyBuffer(wavesurfer.backend.buffer, 0, startTime, firstBuffer, 0);

        emptyBuffer = createBuffer(wavesurfer.backend.buffer, endTime-startTime);
    
        secondBuffer = createBuffer(wavesurfer.backend.buffer, totalDuration - endTime);
        copyBuffer(wavesurfer.backend.buffer, endTime, totalDuration, secondBuffer, 0);
    
        var auxBuffer = concatBuffer(firstBuffer, emptyBuffer);
        finalBuffer = concatBuffer(auxBuffer, secondBuffer);

        resetAndLoadNewBuffer(finalBuffer);
    }
}

function setDisabledWhenNoRegion(status) {
    document.querySelector('#delete_region').disabled = status;
    document.querySelector('#empty_region').disabled = status;
    document.querySelector('#get_selection_btn').disabled = status;
    document.querySelector('#zoom_selected_btn').disabled = status;

    document.querySelector('#delete_region').style.pointerEvents = status === true ? 'none' : 'auto';
    document.querySelector('#empty_region').style.pointerEvents = status === true ? 'none' : 'auto';
    document.querySelector('#get_selection_btn').style.pointerEvents = status === true ? 'none' : 'auto';
    document.querySelector('#zoom_selected_btn').style.pointerEvents = status === true ? 'none' : 'auto';
}

function getRegion() {
    var regionList = wavesurfer.regions.list;
    var region = numOfRegions() > 0 ? regionList[Object.keys(regionList)[0]] : null
    return region;
}

function numOfRegions() {
    return Object.keys(wavesurfer.regions.list).length;
}

// Filter related functions
function applyFilter(filterType, frequency, Q, fromCancel = false) {
	var filter = wavesurfer.backend.ac.createBiquadFilter();
	filter.type = filterType;
	filter.frequency.value = frequency;
	filter.Q.value = Q;
	wavesurfer.backend.setFilter(filter);

	if (!fromCancel) {
	    appliedFilters.push({
            filterType: filterType,
            frequency: frequency,
            Q: Q
        });
    }
	return filter;
}

function createKnob(divID, valMin, valMax, label, decimal, defaultValue = 0) {
	var myKnob = pureknob.createKnob(71, 71);
	myKnob.setProperty('valMin', valMin);
	myKnob.setProperty('valMax', valMax);
    myKnob.setProperty('colorFG', '#AB4646');
    myKnob.setProperty('val', defaultValue);
    myKnob.setProperty('angleStart', -0.75 * Math.PI);
    myKnob.setProperty('angleEnd', 0.75 * Math.PI);
    myKnob.setProperty('label', label);
    myKnob.setProperty('colorLabel', '#AB4646');
    myKnob.setProperty('decimal', decimal);
    myKnob.setProperty('textScale', 0.8);
	var node = myKnob.node();
	var elem = document.getElementById(divID);
	elem.appendChild(node);
	return myKnob;
}

function changeKnobValues(knob, valMin, valMax, label, defaultValue) {
    knob.setProperty('valMin', valMin);
    knob.setProperty('valMax', valMax);
    knob.setProperty('label', label);
    knob.setProperty('val', defaultValue);
}


function cancelFilter() {
    applyFilter('allpass', 0, 1,true);
}

function resetFilters() {
	filters_knob.setValue(0);
    applyFilter('allpass', 0, 1);
}

function changePlaybackRate(value) {
    wavesurfer.setPlaybackRate(value);
}

// Key events

function keyUp(event) {
    switch (event.keyCode) {
        case 32: // space bar
            playPause();
            break;
        case 37: // arrow left
            wavesurfer.skipBackward();
            break;
        case 39: // arrow right
            wavesurfer.skipForward();
            break;
    }
}

function keyDown(event) {
    //print(event);
    switch (event.keyCode) {
        case 8: // delete
            if (numOfRegions() > 0) {
                toUndo('buffer', {buffer: wavesurfer.backend.buffer, tooltipTextUndo: 'Undo Delete Region', tooltipTextRedo: 'Redo Delete Region'});
                deleteRegion();
            }
            break;
        case 90: // z
            if ((event.ctrlKey || event.metaKey) && !event.shiftKey) {
                undo();
            } else if ((event.ctrlKey || event.metaKey) && event.shiftKey) {
                redo();
            }
            break;
        case 187:  //+
            zoomIn();
            break;
        case 189: //-
            zoomOut();
            break;
    }
}