import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Mic,
  Play,
  Square,
  Trash2,
  Volume2,
  VolumeX,
  Radio,
  Phone,
  PhoneOff,
  Loader2
} from 'lucide-react';

const API_BASE = '/api';

interface TestFile {
  filename: string;
  url: string;
  size_bytes: number;
  created: string;
}

export function AudioTest() {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<string | null>(null);
  const [audioStats, setAudioStats] = useState<{max_amplitude: number; rms: number; peak_db: number} | null>(null);
  const [testFiles, setTestFiles] = useState<TestFile[]>([]);
  const [playingFile, setPlayingFile] = useState<string | null>(null);

  // Talkback state
  const [talkbackActive, setTalkbackActive] = useState(false);
  const [talkbackConnecting, setTalkbackConnecting] = useState(false);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<ScriptProcessorNode | null>(null);

  // Local recording for playback
  const [localRecording, setLocalRecording] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    loadTestFiles();
  }, []);

  const loadTestFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/audio/test_files`);
      const data = await res.json();
      setTestFiles(data.files || []);
    } catch (err) {
      console.error('Failed to load test files:', err);
    }
  };

  const recordServerAudio = async () => {
    try {
      setIsRecording(true);
      setRecordedAudio(null);
      setAudioStats(null);

      const res = await fetch(`${API_BASE}/audio/record_test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: 5, sample_rate: 16000 })
      });

      const data = await res.json();

      if (data.success) {
        setRecordedAudio(data.url);
        setAudioStats({
          max_amplitude: data.max_amplitude,
          rms: data.rms,
          peak_db: data.peak_db
        });
        loadTestFiles();
      } else {
        alert('Recording failed: ' + (data.error || 'Unknown error'));
      }
    } catch (err: any) {
      alert('Recording failed: ' + err.message);
    } finally {
      setIsRecording(false);
    }
  };

  const playSpeakerTest = async () => {
    try {
      const res = await fetch(`${API_BASE}/audio/speaker_test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: 2, frequency: 440 })
      });
      const data = await res.json();
      if (!data.success) {
        alert('Speaker test failed: ' + data.error);
      }
    } catch (err: any) {
      alert('Speaker test failed: ' + err.message);
    }
  };

  const playAudio = async (url: string, filename: string) => {
    setPlayingFile(filename);
    const audio = new Audio(url);
    audio.onended = () => setPlayingFile(null);
    audio.play();
  };

  const deleteFile = async (filename: string) => {
    try {
      await fetch(`${API_BASE}/audio/delete_test/${filename}`, { method: 'DELETE' });
      loadTestFiles();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  // ============================================================================
  // TALKBACK - Stream from browser mic to HP speaker
  // ============================================================================

  const startTalkback = async () => {
    try {
      setTalkbackConnecting(true);

      // Check if getUserMedia is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Microphone access requires HTTPS or localhost. Please use http://localhost:5000 instead of the IP address, or enable HTTPS.');
      }

      // 1. Start talkback on server
      const res = await fetch(`${API_BASE}/talkback/start`, { method: 'POST' });
      const data = await res.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to start talkback on server');
      }

      // 2. Get browser mic
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      });
      mediaStreamRef.current = stream;

      // 3. Create audio context and processor
      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      workletRef.current = processor;

      processor.onaudioprocess = async (e) => {
        const inputData = e.inputBuffer.getChannelData(0);

        // Convert float32 to int16 PCM
        const int16Data = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          int16Data[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32767));
        }

        // Send to server
        try {
          await fetch(`${API_BASE}/talkback/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: int16Data.buffer
          });
        } catch (err) {
          // Silently fail - server might be overloaded
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      setTalkbackActive(true);
      setTalkbackConnecting(false);
    } catch (err: any) {
      console.error('Talkback error:', err);
      alert('Failed to start talkback: ' + err.message);
      stopTalkback();
      setTalkbackConnecting(false);
    }
  };

  const stopTalkback = async () => {
    // Stop local audio
    if (workletRef.current) {
      workletRef.current.disconnect();
      workletRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(t => t.stop());
      mediaStreamRef.current = null;
    }

    // Stop server
    try {
      await fetch(`${API_BASE}/talkback/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop server talkback:', err);
    }

    setTalkbackActive(false);
    setTalkbackConnecting(false);
  };

  // ============================================================================
  // LOCAL RECORDING - Record and play back locally
  // ============================================================================

  const startLocalRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        setLocalRecording(url);
        stream.getTracks().forEach(t => t.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err: any) {
      alert('Failed to start recording: ' + err.message);
    }
  };

  const stopLocalRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Talkback - Real-time streaming */}
      <Card className={talkbackActive ? "border-green-500 bg-green-50" : ""}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {talkbackActive ? (
              <Radio className="w-5 h-5 text-green-600 animate-pulse" />
            ) : (
              <Phone className="w-5 h-5" />
            )}
            Live Talkback
          </CardTitle>
          <CardDescription>
            Speak from your browser - audio plays on HP laptop speaker in real-time
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Button
              onClick={talkbackActive ? stopTalkback : startTalkback}
              disabled={talkbackConnecting}
              variant={talkbackActive ? "destructive" : "default"}
              size="lg"
            >
              {talkbackConnecting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Connecting...
                </>
              ) : talkbackActive ? (
                <>
                  <PhoneOff className="w-4 h-4 mr-2" />
                  Stop Talkback
                </>
              ) : (
                <>
                  <Phone className="w-4 h-4 mr-2" />
                  Start Talkback
                </>
              )}
            </Button>

            {talkbackActive && (
              <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse" />
                LIVE - Speak now!
              </Badge>
            )}
          </div>

          <p className="text-sm text-stone-500">
            {talkbackActive
              ? "Your voice is being streamed to HP laptop speakers. Speak into your mic!"
              : "Click to start - your browser mic will stream to HP speaker in real-time"
            }
          </p>
        </CardContent>
      </Card>

      {/* Mic Test */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mic className="w-5 h-5" />
              Mic Test (Server Recording)
            </CardTitle>
            <CardDescription>
              Record 5 seconds on HP mic and play back
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              onClick={recordServerAudio}
              disabled={isRecording}
              variant="outline"
              className="w-full"
            >
              {isRecording ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Recording 5s...
                </>
              ) : (
                <>
                  <Mic className="w-4 h-4 mr-2" />
                  Record 5 Seconds
                </>
              )}
            </Button>

            {recordedAudio && (
              <div className="p-4 bg-stone-50 rounded-lg space-y-3">
                <div className="flex items-center gap-3">
                  <Button
                    onClick={() => playAudio(recordedAudio, 'new')}
                    size="sm"
                  >
                    <Play className="w-4 h-4 mr-1" />
                    Play
                  </Button>
                  <span className="text-sm text-stone-600">Latest recording</span>
                </div>

                {audioStats && (
                  <div className="text-sm space-y-1">
                    <div className="flex justify-between">
                      <span className="text-stone-500">Peak Level:</span>
                      <span className="font-mono">{(audioStats.max_amplitude * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-stone-500">RMS:</span>
                      <span className="font-mono">{(audioStats.rms * 100).toFixed(2)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-stone-500">Peak dB:</span>
                      <span className="font-mono">{audioStats.peak_db} dB</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Speaker Test */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Volume2 className="w-5 h-5" />
              Speaker Test
            </CardTitle>
            <CardDescription>
              Play a test tone on HP laptop speaker
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button onClick={playSpeakerTest} className="w-full">
              <Volume2 className="w-4 h-4 mr-2" />
              Play Test Tone (440Hz)
            </Button>

            <p className="text-sm text-stone-500">
              This plays a 2-second A4 note (440Hz) on the HP laptop speakers.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Local Recording */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="w-5 h-5" />
            Local Record (Browser Mic)
          </CardTitle>
          <CardDescription>
            Record in browser - useful for testing your Mac mic before talkback
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Button
              onClick={isRecording ? stopLocalRecording : startLocalRecording}
              variant={isRecording ? "destructive" : "outline"}
            >
              {isRecording ? (
                <>
                  <Square className="w-4 h-4 mr-2" />
                  Stop Recording
                </>
              ) : (
                <>
                  <Mic className="w-4 h-4 mr-2" />
                  Start Recording
                </>
              )}
            </Button>

            {localRecording && (
              <audio controls src={localRecording} className="flex-1 h-10" />
            )}
          </div>
        </CardContent>
      </Card>

      {/* Test Files History */}
      <Card>
        <CardHeader>
          <CardTitle>Recorded Test Files (on HP)</CardTitle>
          <CardDescription>Previously recorded audio tests stored on server</CardDescription>
        </CardHeader>
        <CardContent>
          {testFiles.length === 0 ? (
            <p className="text-stone-500 text-sm">No recordings yet</p>
          ) : (
            <div className="space-y-2">
              {testFiles.map((file) => (
                <div key={file.filename} className="flex items-center justify-between p-3 bg-stone-50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <Button
                      onClick={() => playAudio(file.url, file.filename)}
                      size="sm"
                      variant="ghost"
                    >
                      {playingFile === file.filename ? (
                        <VolumeX className="w-4 h-4" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                    </Button>
                    <div>
                      <p className="text-sm font-medium">{file.filename}</p>
                      <p className="text-xs text-stone-500">
                        {formatSize(file.size_bytes)} • {new Date(file.created).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <Button
                    onClick={() => deleteFile(file.filename)}
                    size="sm"
                    variant="ghost"
                    className="text-red-500 hover:text-red-700"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
