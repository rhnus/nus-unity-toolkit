using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.TestTools.TestRunner.Api;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NUS.AgentTools
{
    /// <summary>
    /// EditMode test runs for agents driving a SHARED editor through Unity_RunCommand (see the run-unity-tests
    /// skill, which calls it by name because Unity_RunCommand can't reference package code). Several agents and the
    /// user may use the editor at once, so every entry point answers immediately instead of waiting: BUSY when
    /// another agent holds the editor, NOT RUN when it is compiling, playing, or has unsaved scenes (a test run
    /// would stop on Unity's save prompt until a human clicks).
    ///
    ///   1. AgentTestRunner.Compile("my-agent-name");   // reserves the editor, imports changed scripts
    ///   2. AgentTestRunner.Run(new[] { "^FollowUpEventTests" }, "my-agent-name");   // next command; releases
    /// </summary>
    public static class AgentTestRunner
    {
        // Per project, so the list stays with the tests it describes rather than with the shared skill.
        const string KnownFailuresPath = ".claude/known-test-failures.txt";
        const string LockPath = "Library/AgentTools/editor-lock.txt";
        static readonly TimeSpan LockLifetime = TimeSpan.FromMinutes(10);

        /// <summary>
        /// Reserves the editor for <paramref name="owner"/> and imports changed files. Unity recompiles only if a
        /// script actually changed, so a call with nothing new costs other agents nothing.
        /// </summary>
        public static string Compile(string owner)
        {
            string holder = TryReserve(owner);
            if (holder != null) return Busy(holder);
            if (EditorApplication.isPlaying) { Release(owner); return "NOT RUN: play mode. Do not stop it; ask."; }

            AssetDatabase.Refresh();
            return EditorApplication.isCompiling
                ? "Compiling changed scripts. Call Run in the next command."
                : "No script changes to compile. Call Run now.";
        }

        /// <summary>
        /// Runs EditMode tests synchronously and releases the reservation. <paramref name="groupPatterns"/> are
        /// regexes on the full test name; null runs the whole suite, which blocks the editor for minutes.
        /// </summary>
        public static string Run(string[] groupPatterns, string owner, string resultsPath = null)
        {
            string holder = TryReserve(owner);
            if (holder != null) return Busy(holder);
            try
            {
                if (EditorApplication.isPlaying) return "NOT RUN: play mode. Do not stop it; ask.";
                if (EditorApplication.isCompiling) return "NOT RUN: still compiling. Try Run once more shortly.";
                if (EditorUtility.scriptCompilationFailed)
                    return "NOT RUN: the last script compile FAILED, so tests would run stale code. Read the console errors.";
                string dirty = DirtySceneNames();
                if (dirty != null)
                    return $"NOT RUN: unsaved changes in {dirty}. A test run would stop on Unity's save prompt. Ask the user.";

                var collector = new Collector();
                var api = ScriptableObject.CreateInstance<TestRunnerApi>();
                api.RegisterCallbacks(collector);
                try
                {
                    var filter = new Filter { testMode = TestMode.EditMode };
                    if (groupPatterns != null && groupPatterns.Length > 0) filter.groupNames = groupPatterns;
                    // Synchronous because an asynchronous run's callbacks are lost when the command returns.
                    api.Execute(new ExecutionSettings(filter) { runSynchronously = true });
                }
                finally
                {
                    api.UnregisterCallbacks(collector);
                    UnityEngine.Object.DestroyImmediate(api);
                }

                string summary = Summarise(collector, LoadKnownFailures());
                if (!string.IsNullOrEmpty(resultsPath)) File.WriteAllText(resultsPath, summary);
                return summary;
            }
            finally
            {
                Release(owner);
            }
        }

        /// <summary>Who holds the editor, or null if it is free. For a status check without reserving.</summary>
        public static string Holder()
        {
            if (!File.Exists(LockPath)) return null;
            string[] parts = File.ReadAllText(LockPath).Split('|');
            if (parts.Length < 2 || !long.TryParse(parts[1], out long ticks)) return null;
            var since = new DateTime(ticks, DateTimeKind.Utc);
            return DateTime.UtcNow - since > LockLifetime ? null : $"{parts[0]} since {since:HH:mm} UTC";
        }

        // Returns the other holder, or null once the reservation is ours (fresh or renewed). A reservation older
        // than LockLifetime counts as abandoned, so a crashed agent cannot hold the editor forever.
        static string TryReserve(string owner)
        {
            owner = OwnerName(owner);
            string holder = Holder();
            if (holder != null && !holder.StartsWith(owner + " since ")) return holder;

            Directory.CreateDirectory(Path.GetDirectoryName(LockPath));
            File.WriteAllText(LockPath, $"{owner}|{DateTime.UtcNow.Ticks}");
            return null;
        }

        /// <summary>Frees the editor after a <see cref="Compile"/> that is not followed by <see cref="Run"/>.</summary>
        public static void Release(string owner)
        {
            string holder = Holder();
            if (holder != null && holder.StartsWith(OwnerName(owner) + " since ")) File.Delete(LockPath);
        }

        static string OwnerName(string owner) =>
            string.IsNullOrWhiteSpace(owner) ? "unnamed-agent" : owner.Replace("|", "/").Trim();

        static string Busy(string holder) =>
            $"BUSY: the editor is reserved by {holder}. Do not wait or retry in a loop; use unity-compile-check " +
            "and report that the tests were not run.";

        static string DirtySceneNames()
        {
            var names = new List<string>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                Scene s = SceneManager.GetSceneAt(i);
                if (s.isDirty) names.Add(string.IsNullOrEmpty(s.name) ? "an untitled scene" : s.name);
            }
            return names.Count > 0 ? string.Join(", ", names) : null;
        }

        static HashSet<string> LoadKnownFailures()
        {
            if (!File.Exists(KnownFailuresPath)) return new HashSet<string>();
            return new HashSet<string>(File.ReadAllLines(KnownFailuresPath)
                .Select(l => l.Trim())
                .Where(l => l.Length > 0 && !l.StartsWith("#")));
        }

        static string Summarise(Collector c, HashSet<string> known)
        {
            var fresh = c.Failures.Where(f => !known.Contains(f.name)).ToList();
            var stillKnown = c.Failures.Where(f => known.Contains(f.name)).ToList();

            var sb = new StringBuilder();
            sb.Append($"pass={c.Passed} fail={c.Failures.Count} (new={fresh.Count}, known={stillKnown.Count}) skip={c.Skipped}\n");
            if (c.Passed + c.Failures.Count + c.Skipped == 0)
                sb.Append("WARNING: no tests ran. Check the group patterns, or that the test file has compiled.\n");

            foreach (var f in fresh) sb.Append($"NEW FAIL {f.name}: {f.message}\n");
            foreach (var f in stillKnown) sb.Append($"known fail {f.name}\n");
            return sb.ToString();
        }

        sealed class Collector : ICallbacks
        {
            public readonly List<(string name, string message)> Failures = new();
            public int Passed, Skipped;

            public void RunStarted(ITestAdaptor testsToRun) { }
            public void RunFinished(ITestResultAdaptor result) { }
            public void TestStarted(ITestAdaptor test) { }

            public void TestFinished(ITestResultAdaptor result)
            {
                if (result.HasChildren) return;
                switch (result.TestStatus)
                {
                    case TestStatus.Passed: Passed++; break;
                    case TestStatus.Skipped: Skipped++; break;
                    case TestStatus.Failed:
                        string first = (result.Message ?? string.Empty).Split('\n')[0].Trim();
                        Failures.Add((result.FullName, first));
                        break;
                }
            }
        }
    }
}
