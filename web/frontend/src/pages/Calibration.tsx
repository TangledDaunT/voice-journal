import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ProgressBar } from '@/components/ui/progress';
import {
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Activity,
  Check,
  X,
  AlertTriangle,
  RefreshCw,
  Save,
  Settings
} from 'lucide-react';
import { calibrationApi } from '@/lib/api';

interface AudioDevice {
  index: number;
  name: string;
  channels: number;
  default_sample_rate: number;
  is_default: boolean;
}

interface SilentProfile {
  recorded_at: string;
  rms_level: number;
  max_amplitude: number;
  peak_frequency_hz: number;
  recommended_vad_threshold: number;
  noise_floor_db: number;
}

interface VoiceProfile {
  name: string;
  recorded_at: string;
  rms_level: number;
  max_amplitude: number;
  estimated_pitch_hz: number;
  spectral_centroid_hz: number;
}

interface LevelTest {
  rms: number;
  max_amplitude: number;
  peak_db: number;
  quality: string;
  message: string;
}

export default function Calibration() {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [silentProfile, setSilentProfile] = useState<SilentProfile | null>(null);
  const [voiceProfiles, setVoiceProfiles] = useState<Record<string, VoiceProfile>>({});
  const [newSpeakerName, setNewSpeakerName] = useState('');
  const [status, setStatus] = useState('idle');
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [levelTest, setLevelTest] = useState<LevelTest | null>(null);

  useEffect(() => {
    loadCalibrationData();
  }, []);

  const loadCalibrationData = async () => {
    try {
      setLoading(true);

      // Get audio devices
      const devicesRes = await calibrationApi.getAudioDevices();
      if (devicesRes.data) {
        setDevices(devicesRes.data);
        const defaultDevice = devicesRes.data.find((d: AudioDevice) => d.is_default);
        if (defaultDevice) {
          setSelectedDevice(defaultDevice.index);
        }
      }

      // Get current calibration status
      const statusRes = await calibrationApi.getStatus();
      if (statusRes.data) {
        setStatus(statusRes.data.status);
        if (statusRes.data.silent_baseline) {
          setSilentProfile(statusRes.data.silent_baseline);
        }
        if (statusRes.data.voice_profiles) {
          setVoiceProfiles(statusRes.data.voice_profiles);
        }
      }
    } catch (err) {
      setError('Failed to load calibration data');
    } finally {
      setLoading(false);
    }
  };

  const recordSilentBaseline = async () => {
    try {
      setIsRecording(true);
      setError(null);
      setStatus('recording_silent');

      const res = await calibrationApi.recordSilentBaseline();

      if (res.data?.success) {
        setSilentProfile(res.data.profile);
        setStatus('idle');
      } else {
        setError(res.data?.error || 'Failed to record silent baseline');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Recording failed');
    } finally {
      setIsRecording(false);
      setStatus('idle');
    }
  };

  const recordVoiceSample = async () => {
    if (!newSpeakerName.trim()) {
      setError('Please enter a speaker name');
      return;
    }

    try {
      setIsRecording(true);
      setError(null);

      const res = await calibrationApi.recordVoiceSample(newSpeakerName.trim());

      if (res.data?.success) {
        setVoiceProfiles(prev => ({
          ...prev,
          [newSpeakerName.trim()]: res.data.profile
        }));
        setNewSpeakerName('');
      } else {
        setError(res.data?.error || 'Failed to record voice sample');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Recording failed');
    } finally {
      setIsRecording(false);
    }
  };

  const testLevels = async () => {
    try {
      setIsRecording(true);
      setError(null);

      const res = await calibrationApi.testLevels();

      if (res.data?.success) {
        setLevelTest(res.data);
      } else {
        setError(res.data?.error || 'Level test failed');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Level test failed');
    } finally {
      setIsRecording(false);
    }
  };

  const applyCalibration = async () => {
    try {
      setLoading(true);
      const res = await calibrationApi.apply();

      if (res.data?.success) {
        setError(null);
        alert('Calibration applied! Restart daemon for full effect.');
      } else {
        setError(res.data?.error || 'Failed to apply calibration');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Apply failed');
    } finally {
      setLoading(false);
    }
  };

  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'good': return 'text-green-600';
      case 'acceptable': return 'text-yellow-600';
      case 'too_low': return 'text-red-600';
      case 'clipping': return 'text-red-600';
      default: return 'text-stone-500';
    }
  };

  const getQualityIcon = (quality: string) => {
    switch (quality) {
      case 'good': return <Check className="w-5 h-5 text-green-600" />;
      case 'acceptable': return <AlertTriangle className="w-5 h-5 text-yellow-600" />;
      case 'too_low': return <X className="w-5 h-5 text-red-600" />;
      case 'clipping': return <AlertTriangle className="w-5 h-5 text-red-600" />;
      default: return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-serif font-bold text-stone-900">Audio Calibration</h1>
        <p className="text-stone-600 mt-1">Configure your microphone and set noise baseline</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" />
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Audio Devices */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5" />
              Audio Input Device
            </CardTitle>
            <CardDescription>Select which microphone to use for recording</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {devices.map((device) => (
                <div
                  key={device.index}
                  onClick={() => setSelectedDevice(device.index)}
                  className={`p-3 border rounded-lg cursor-pointer transition-all ${
                    selectedDevice === device.index
                      ? 'border-amber-500 bg-amber-50'
                      : 'border-stone-200 hover:border-stone-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {selectedDevice === device.index ? (
                        <Mic className="w-5 h-5 text-amber-600" />
                      ) : (
                        <MicOff className="w-5 h-5 text-stone-400" />
                      )}
                      <div>
                        <p className="font-medium text-stone-900">
                          {device.name}
                          {device.is_default && (
                            <Badge variant="outline" className="ml-2 text-xs">Default</Badge>
                          )}
                        </p>
                        <p className="text-sm text-stone-500">
                          {device.channels} channels • {device.default_sample_rate}Hz
                        </p>
                      </div>
                    </div>
                    {selectedDevice === device.index && (
                      <Check className="w-5 h-5 text-amber-600" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Level Test */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="w-5 h-5" />
              Input Level Test
            </CardTitle>
            <CardDescription>Check if your microphone is working properly</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              onClick={testLevels}
              disabled={isRecording}
              className="w-full"
            >
              {isRecording && status !== 'recording_silent' ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Recording 3s...
                </>
              ) : (
                <>
                  <Volume2 className="w-4 h-4 mr-2" />
                  Test Levels (3 sec)
                </>
              )}
            </Button>

            {levelTest && (
              <div className="space-y-4 p-4 bg-stone-50 rounded-lg">
                <div className="flex items-center justify-between">
                  <span className="text-stone-600">Quality:</span>
                  <span className={`flex items-center gap-2 font-medium ${getQualityColor(levelTest.quality)}`}>
                    {getQualityIcon(levelTest.quality)}
                    {levelTest.quality.replace('_', ' ')}
                  </span>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-stone-500">Peak Level</span>
                    <span className="font-mono">{(levelTest.max_amplitude * 100).toFixed(1)}%</span>
                  </div>
                  <ProgressBar value={levelTest.max_amplitude * 100} className="h-2" />
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-stone-500">Peak Volume</span>
                  <span className="font-mono">{levelTest.peak_db} dB</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-stone-500">RMS Level</span>
                  <span className="font-mono">{(levelTest.rms * 100).toFixed(2)}%</span>
                </div>
                <p className="text-sm text-stone-600 mt-2">{levelTest.message}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Silent Room Baseline */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <VolumeX className="w-5 h-5" />
              Room Noise Baseline
            </CardTitle>
            <CardDescription>
              Record 5 seconds with no talking to set the noise floor
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-stone-600">
              Sit quietly in the room for 5 seconds. This helps the system understand
              background noise levels (fans, traffic, etc.)
            </p>

            <Button
              onClick={recordSilentBaseline}
              disabled={isRecording}
              variant={silentProfile ? "outline" : "default"}
              className="w-full"
            >
              {isRecording && status === 'recording_silent' ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Recording 5s...
                </>
              ) : silentProfile ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Re-record Baseline
                </>
              ) : (
                <>
                  <Mic className="w-4 h-4 mr-2" />
                  Record Silent Baseline (5 sec)
                </>
              )}
            </Button>

            {silentProfile && (
              <div className="p-4 bg-stone-50 rounded-lg space-y-3">
                <div className="flex items-center gap-2 text-green-600 mb-2">
                  <Check className="w-5 h-5" />
                  <span className="font-medium">Baseline recorded</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="text-stone-500">Noise Floor:</div>
                  <div className="font-mono">{silentProfile.noise_floor_db} dB</div>
                  <div className="text-stone-500">RMS Level:</div>
                  <div className="font-mono">{(silentProfile.rms_level * 1000).toFixed(2)}k</div>
                  <div className="text-stone-500">Peak Freq:</div>
                  <div className="font-mono">{silentProfile.peak_frequency_hz} Hz</div>
                  <div className="text-stone-500">Recommended VAD:</div>
                  <div className="font-mono">{silentProfile.recommended_vad_threshold}</div>
                </div>
                <p className="text-xs text-stone-400 mt-2">
                  Recorded: {new Date(silentProfile.recorded_at).toLocaleString()}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Voice Profiles */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mic className="w-5 h-5" />
              Speaker Voice Profiles
            </CardTitle>
            <CardDescription>
              Record 5 seconds of each person speaking to identify them
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Enter speaker name (e.g., Shreyansh)"
                value={newSpeakerName}
                onChange={(e) => setNewSpeakerName(e.target.value)}
                className="flex-1"
              />
              <Button
                onClick={recordVoiceSample}
                disabled={isRecording || !newSpeakerName.trim()}
              >
                {isRecording ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Mic className="w-4 h-4" />
                )}
              </Button>
            </div>

            {Object.keys(voiceProfiles).length > 0 && (
              <div className="space-y-3">
                {Object.entries(voiceProfiles).map(([name, profile]) => (
                  <div key={name} className="p-3 bg-stone-50 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-stone-900">{name}</span>
                      <Badge variant="outline">Calibrated</Badge>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      <div>
                        <span className="text-stone-500">Pitch:</span>
                        <span className="ml-1 font-mono">{profile.estimated_pitch_hz} Hz</span>
                      </div>
                      <div>
                        <span className="text-stone-500">Max:</span>
                        <span className="ml-1 font-mono">{(profile.max_amplitude * 100).toFixed(0)}%</span>
                      </div>
                      <div>
                        <span className="text-stone-500">Bright:</span>
                        <span className="ml-1 font-mono">{profile.spectral_centroid_hz} Hz</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Apply Button */}
      {silentProfile && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-medium text-stone-900">Calibration Ready</h3>
                <p className="text-sm text-stone-600">
                  Apply settings and restart the daemon for changes to take effect
                </p>
              </div>
              <Button onClick={applyCalibration} disabled={loading}>
                <Save className="w-4 h-4 mr-2" />
                Apply Calibration
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
