import { useQuery } from '@tanstack/react-query'
import { fetchConversations, fetchConversation, searchConversations } from '@/lib/api'
import { Conversation } from '@/lib/api'

export function useConversations(date?: string, limit = 100) {
  return useQuery<Conversation[]>({
    queryKey: ['conversations', date, limit],
    queryFn: () => fetchConversations(date, limit),
    staleTime: 30000,
  })
}

export function useConversation(id: number) {
  return useQuery<Conversation>({
    queryKey: ['conversation', id],
    queryFn: () => fetchConversation(id),
    enabled: id > 0,
  })
}

export function useSearchConversations(query: string) {
  return useQuery<Conversation[]>({
    queryKey: ['search', query],
    queryFn: () => searchConversations(query),
    enabled: query.length > 2,
    staleTime: 60000,
  })
}
