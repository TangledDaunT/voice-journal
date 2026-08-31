import { useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronRight, ChevronLeft, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'

const WELCOME_STEPS = [
  {
    title: 'Welcome to Voice Journal',
    description: 'Your personal audio journal powered by AI transcription.',
    icon: '🎙️',
  },
  {
    title: 'Automatic Capture',
    description: 'Voice Journal automatically captures conversations when voice is detected.',
    icon: '👂',
  },
  {
    title: 'Batch Processing',
    description: 'Transcription runs during idle times and overnight for better accuracy.',
    icon: '⚡',
  },
  {
    title: 'Search & Review',
    description: 'Easily browse and search through all your past conversations.',
    icon: '🔍',
  },
]

interface OnboardingGuideProps {
  onComplete: () => void
}

export function OnboardingGuide({ onComplete }: OnboardingGuideProps) {
  const [currentStep, setCurrentStep] = useState(0)

  const handleNext = () => {
    if (currentStep < WELCOME_STEPS.length - 1) {
      setCurrentStep(currentStep + 1)
    } else {
      onComplete()
    }
  }

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  const step = WELCOME_STEPS[currentStep]
  const isLastStep = currentStep === WELCOME_STEPS.length - 1

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <motion.div
        key={currentStep}
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -20 }}
        className="space-y-6"
      >
        <div className="text-6xl">{step.icon}</div>
        <h2 className="text-2xl font-bold font-display">{step.title}</h2>
        <p className="text-muted-foreground max-w-md">{step.description}</p>
      </motion.div>

      <div className="mt-8 flex items-center gap-2">
        {WELCOME_STEPS.map((_, i) => (
          <motion.div
            key={i}
            className={`h-2 rounded-full transition-colors ${
              i <= currentStep ? 'bg-primary w-6' : 'bg-muted w-2'
            }`}
          />
        ))}
      </div>

      <div className="mt-8 flex gap-4">
        {currentStep > 0 && (
          <Button variant="outline" onClick={handlePrev}>
            <ChevronLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
        )}
        <Button onClick={handleNext}>
          {isLastStep ? (
            <>
              <Check className="mr-2 h-4 w-4" />
              Get Started
            </>
          ) : (
            <>
              Next
              <ChevronRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  )
}
