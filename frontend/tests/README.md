# UI acceptance — owner 3

Test on real Chrome/Edge with a microphone on localhost or HTTPS.
Cover permission denial, no input, start/stop, replay, new session, API failure, 10-turn limit.
Ensure raw transcript and result are rendered with textContent, never unsafe innerHTML.
Voice test matrix: RU, KK, mixed; check actual audible speech on the demo machine.
Do not treat browser speechSynthesis as guaranteed Kazakh support.
Only report end-to-audio after actual playback begins; null means not measured.
Add automated UI checks under this folder if a frontend toolchain is introduced.
