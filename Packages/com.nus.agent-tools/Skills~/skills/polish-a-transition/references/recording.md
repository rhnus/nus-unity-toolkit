# Recording a beat

A still can't show motion. To judge a transition, or to prove a fix, record a short clip with Unity's Recorder
(`com.unity.recorder`). If the project doesn't have it, ask before adding a package.

## Driving it from Unity_RunCommand

Each command is compiled fresh, so a static field doesn't survive from the call that starts the recording to
the one that stops it. Keep the controller in the AppDomain:

```csharp
using UnityEditor.Recorder;
using UnityEditor.Recorder.Input;

var settings = ScriptableObject.CreateInstance<RecorderControllerSettings>();
var movie = ScriptableObject.CreateInstance<MovieRecorderSettings>();
movie.Enabled = true;
movie.ImageInputSettings = new GameViewInputSettings { OutputWidth = 1280, OutputHeight = 720 };
movie.AudioInputSettings.PreserveAudio = false;
movie.OutputFile = System.IO.Path.GetFullPath("<captures folder>/<name>");   // .mp4 is added
settings.AddRecorderSettings(movie);
settings.SetRecordModeToManual();
settings.FrameRate = 30;
settings.CapFrameRate = true;
var controller = new RecorderController(settings);
controller.PrepareRecording();
controller.StartRecording();
System.AppDomain.CurrentDomain.SetData("polish.recorder", controller);
```

Stop it in a later call with
`(System.AppDomain.CurrentDomain.GetData("polish.recorder") as RecorderController)?.StopRecording()`, then clear
the slot. The recorder needs Play Mode; get to the beat first, then start recording.

## What decides the clip's length

- **Frames, not seconds.** With a capped frame rate the video advances one frame per game frame, so it plays
  smoothly whatever the editor's real speed, but a slow editor makes the real wait long.
- **Resolution is the cost.** Encoding 1080p every frame can hold the editor near one frame a second;
  720p is enough to judge motion and encodes far faster.
- **Unfocused editors throttle.** Ask the person to keep the Game view focused while it records.
- **Hold in frames.** Between actions, wait until enough frames have passed (read `Time.frameCount`), not for
  a fixed number of seconds: about 60-90 frames for a beat to read on screen.
- **Typing dialogue eats time.** At a low frame rate each line takes a long time to type out. Move it on with
  the dialogue's own continue control, as a player would, not with a call that ends the conversation (that
  can advance the game past the activity).

Keep clips in the project's ignored captures folder, never in the repository.
