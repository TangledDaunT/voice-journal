import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ToastType = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
}

interface ToastProps {
  toast: Toast
  onClose: (id: string) => void
}

const icons: Record<ToastType, React.ElementType> = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
}

const colors: Record<ToastType, string> = {
  success: 'bg-accent text-accent-foreground',
  error: 'bg-destructive text-destructive-foreground',
  info: 'bg-primary text-primary-foreground',
}

export function ToastItem({ toast, onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(() => onClose(toast.id), 5000)
    return () => clearTimeout(timer)
  }, [toast.id, onClose])

  const Icon = icons[toast.type]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.95 }}
      className={cn(
        'flex items-start gap-3 rounded-lg border border-border/50 p-4 shadow-lg',
        'bg-card text-card-foreground'
      )}
    >
      <div className={cn('rounded-full p-1', colors[toast.type])}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1">
        <p className="font-medium">{toast.title}</p>
        {toast.message && (
          <p className="mt-1 text-sm text-muted-foreground">{toast.message}</p>
        )}
      </div>
      <button
        onClick={() => onClose(toast.id)}
        className="rounded-lg p-1 text-muted-foreground hover:bg-muted/10 hover:text-foreground"
      >
        <X className="h-4 w-4" />
      </button>
    </motion.div>
  )
}

export function ToastContainer({
  toasts,
  onClose,
}: {
  toasts: Toast[]
  onClose: (id: string) => void
}) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onClose={onClose} />
        ))}
      </AnimatePresence>
    </div>
  )
}

export type AddToast = (toast: Omit<Toast, 'id'>) => void

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast: AddToast = (toast) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { ...toast, id }])
  }

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return { toasts, addToast, removeToast }
}
