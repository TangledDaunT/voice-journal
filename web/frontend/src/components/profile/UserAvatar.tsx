import { motion } from 'framer-motion'

interface UserAvatarProps {
  name: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-10 w-10 text-sm',
  lg: 'h-12 w-12 text-base',
}

const colors = [
  'from-primary to-secondary',
  'from-secondary to-accent',
  'from-accent to-primary',
  'from-primary/80 to-accent/80',
]

// Stable color based on name
function getColorFromName(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

export function UserAvatar({ name, size = 'md', className }: UserAvatarProps) {
  const initial = name.charAt(0).toUpperCase()
  const gradient = getColorFromName(name)

  return (
    <motion.div
      whileHover={{ scale: 1.05 }}
      className={`relative flex items-center justify-center rounded-full bg-gradient-to-br ${gradient} ${sizes[size]} ${className || ''}`}
    >
      {initial}
    </motion.div>
  )
}

export function UserAvatarWithStatus({ name, isOnline }: UserAvatarProps & { isOnline?: boolean }) {
  return (
    <div className="relative">
      <UserAvatar name={name} />
      {isOnline !== undefined && (
        <span
          className={`absolute bottom-0 right-0 block h-2.5 w-2.5 rounded-full ring-2 ring-background ${
            isOnline ? 'bg-accent' : 'bg-muted'
          }`}
        />
      )}
    </div>
  )
}
