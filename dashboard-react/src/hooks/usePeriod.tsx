import { createContext, useContext, useState, type ReactNode } from 'react';

type Period = 7 | 14 | 30 | 90;

interface PeriodContextValue {
  days: Period;
  setDays: (d: Period) => void;
}

const PeriodContext = createContext<PeriodContextValue>({ days: 7, setDays: () => {} });

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [days, setDays] = useState<Period>(7);
  return (
    <PeriodContext.Provider value={{ days, setDays }}>
      {children}
    </PeriodContext.Provider>
  );
}

export function usePeriod() {
  return useContext(PeriodContext);
}
