import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import type { VisualizerState } from '../visualizer/types'

interface VisualizerStateContextValue {
  state: VisualizerState
  setState: (state: VisualizerState) => void
}

const VisualizerStateContext = createContext<VisualizerStateContextValue | undefined>(undefined)

interface VisualizerStateProviderProps {
  children: ReactNode
}

export function VisualizerStateProvider({ children }: VisualizerStateProviderProps) {
  const [state, setState] = useState<VisualizerState>('IDLE')

  const setVisualizerState = useCallback((newState: VisualizerState) => {
    setState(newState)
  }, [])

  return (
    <VisualizerStateContext.Provider value={{ state, setState: setVisualizerState }}>
      {children}
    </VisualizerStateContext.Provider>
  )
}

export function useVisualizerState(): VisualizerStateContextValue {
  const ctx = useContext(VisualizerStateContext)
  if (ctx === undefined) {
    throw new Error('useVisualizerState must be used within a VisualizerStateProvider')
  }
  return ctx
}
