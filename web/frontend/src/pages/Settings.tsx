import { useState } from 'react'
import { Settings2, Mic, Bell, Moon, Trash2, Download, Info } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function Settings() {
  const [darkMode, setDarkMode] = useState(false)

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Manage your voice journal preferences</p>
      </div>

      {/* Voice Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5" />
            Voice Profiles
          </CardTitle>
          <CardDescription>
            Calibrate speaker recognition for better accuracy
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg bg-muted/30 p-4">
            <div>
              <p className="font-medium">Shreyansh</p>
              <p className="text-sm text-muted-foreground">Primary voice profile</p>
            </div>
            <Button variant="outline" size="sm" disabled>
              Calibrate
            </Button>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-muted/30 p-4">
            <div>
              <p className="font-medium">Shivangi</p>
              <p className="text-sm text-muted-foreground">Secondary voice profile</p>
            </div>
            <Button variant="outline" size="sm" disabled>
              Calibrate
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Appearance */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Moon className="h-5 w-5" />
            Appearance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Dark Mode</p>
              <p className="text-sm text-muted-foreground">
                Use dark earth tones theme
              </p>
            </div>
            <button
              onClick={() => setDarkMode(!darkMode)}
              className={`relative h-6 w-11 rounded-full transition-colors ${darkMode ? 'bg-primary' : 'bg-muted'
                }`}
            >
              <span
                className={`absolute left-0.5 top-0.5 block h-5 w-5 rounded-full bg-white transition-transform ${darkMode ? 'translate-x-5' : ''
                  }`}
              />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Notifications
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Browser Notifications</p>
              <p className="text-sm text-muted-foreground">
                Get notified when new conversations are captured
              </p>
            </div>
            <Button variant="outline" size="sm" disabled>
              Enable
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Data Management */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            Data Management
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button variant="outline" className="w-full justify-start gap-2" disabled>
            <Download className="h-4 w-4" />
            Export All Conversations
          </Button>
          <Button
            variant="outline"
            className="w-full justify-start gap-2 text-destructive hover:text-destructive"
            disabled
          >
            <Trash2 className="h-4 w-4" />
            Clear All Data
          </Button>
        </CardContent>
      </Card>

      {/* About */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="h-5 w-5" />
            About
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm text-muted-foreground">
            <p><strong>Version:</strong> 2.0.0 (Batch Mode)</p>
            <p><strong>Architecture:</strong> Batch processing with large-v3 model</p>
            <p><strong>Deployment:</strong> HP Laptop via Tailscale</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
