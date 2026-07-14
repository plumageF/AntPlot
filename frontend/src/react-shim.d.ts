declare module "react" {
  export type ReactNode = any;
  export type SetStateAction<S> = S | ((prevState: S) => S);
  export type Dispatch<A> = (value: A) => void;
  export interface MutableRefObject<T> {
    current: T;
  }
  export function useState<S>(initialState: S | (() => S)): [S, Dispatch<SetStateAction<S>>];
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useMemo<T>(factory: () => T, deps?: readonly unknown[]): T;
  export function useRef<T>(initialValue: T): MutableRefObject<T>;
  const React: { createElement: (...args: any[]) => any };
  export default React;
}

declare namespace React {
  type ReactNode = any;
  type SetStateAction<S> = S | ((prevState: S) => S);
  type Dispatch<A> = (value: A) => void;
  type DispatchWithoutAction = () => void;
}

declare module "react-dom/client" {
  export function createRoot(container: Element | DocumentFragment): { render(children: any): void };
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
  interface IntrinsicAttributes {
    key?: any;
  }
}
