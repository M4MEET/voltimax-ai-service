import { createContext, useContext, useState, type ReactNode } from 'react';

// Any lookback window from 1–365 days. Presets are quick-picks; custom is free-form.
interface PeriodContextValue {
  days: number;
  setDays: (d: number) => void;
}

const PeriodContext = createContext<PeriodContextValue>({ days: 7, setDays: () => {} });

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [days, setDays] = useState<number>(7);
  return (
    <PeriodContext.Provider value={{ days, setDays }}>
      {children}
    </PeriodContext.Provider>
  );
}

export function usePeriod() {
  return useContext(PeriodContext);
}
