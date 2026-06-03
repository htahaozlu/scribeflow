# ScribeFlow demo — recorded with vhs (https://github.com/charmbracelet/vhs).
# Run via scripts/record-demo.sh (it prepares the sample + a warmed model cache).
# The story: transcribe → interrupt → re-run the SAME command → it resumes and finishes.
# Timings are conservative; bump the Sleep values if your machine is slower.

Output demo.gif
Require scribeflow

Set Shell bash
Set FontSize 16
Set Width 1120
Set Height 660
Set Padding 22
Set Theme "Dracula"
Set TypingSpeed 30ms

Hide
Type "clear" Enter
Show

Type "scribeflow transcribe demo.wav --model tiny -l en --format srt --chunk-minutes 1"
Enter
Sleep 7s

# closed the laptop / lost the connection — interrupt it
Ctrl+C
Sleep 1500ms

Type "# interrupted. just run the SAME command again:"
Enter
Type "scribeflow transcribe demo.wav --model tiny -l en --format srt --chunk-minutes 1"
Enter
Sleep 12s

Type "cat scribeflow-output/demo/demo_transcript.txt"
Enter
Sleep 3500ms
