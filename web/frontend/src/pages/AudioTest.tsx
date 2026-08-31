import { AudioTest } from '@/components/audio/AudioTest';

export default function AudioTestPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-serif font-bold text-stone-900">Audio Test</h1>
        <p className="text-stone-600 mt-1">Test microphone and speaker, enable live talkback</p>
      </div>

      <AudioTest />
    </div>
  );
}
