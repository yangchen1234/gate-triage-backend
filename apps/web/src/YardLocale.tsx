import { createContext, useContext, useMemo } from 'react';
import type { ComponentProps, ReactNode } from 'react';
import { Modal } from './Components.tsx';
import type { DemoPort } from './yard-demo.ts';
import { formatYardNumber, formatYardTime, translateYard } from './yard-language.ts';
const YardLocale = createContext<DemoPort>('la');
export function YardLocaleProvider({ port, children }: { port: DemoPort; children: ReactNode }) { return <YardLocale.Provider value={port}>{children}</YardLocale.Provider>; }
export function useYardLocale() {
  const port = useContext(YardLocale);
  return useMemo(() => ({ port, t: <T,>(value: T): T => translateYard(value, port), number: (n: number) => formatYardNumber(n, port), formatTime: (at: string) => formatYardTime(at, port) }), [port]);
}
export function YardModal(props: ComponentProps<typeof Modal>) {
  const { t } = useYardLocale();
  return <Modal {...props} kicker={t('GATE TRIAGE WORKSPACE')} closeLabel={t('Close dialog')} />;
}
