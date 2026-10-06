/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// ── Global JSX & Containerized Types Fallback ────────────────────────────────
// Provides ambient type bindings for host IDEs when node_modules is isolated in Docker.

declare global {
  namespace JSX {
    interface Element extends React.ReactElement<any, any> {}
    interface ElementClass extends React.Component<any> {
      render(): React.ReactNode;
    }
    interface ElementAttributesProperty {
      props: {};
    }
    interface ElementChildrenAttribute {
      children: {};
    }
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

declare module "react/jsx-dev-runtime" {
  export const jsxDEV: any;
  export const Fragment: any;
}

declare module "react" {
  export type ReactNode =
    | ReactElement
    | string
    | number
    | Iterable<ReactNode>
    | ReactPortal
    | boolean
    | null
    | undefined;

  export interface ReactElement<
    P = any,
    T extends string | JSXElementConstructor<any> = string | JSXElementConstructor<any>,
  > {
    type: T;
    props: P;
    key: string | null;
  }

  export type JSXElementConstructor<P> =
    | ((props: P) => ReactElement<any, any> | null)
    | (new (props: P) => Component<any, any>);

  export interface ReactPortal extends ReactElement {
    children: ReactNode;
  }

  export class Component<P = {}, S = {}> {
    constructor(props: P);
    props: Readonly<P>;
    state: Readonly<S>;
    render(): ReactNode;
  }

  export function useState<T>(
    initialState: T | (() => T)
  ): [T, (value: T | ((prevState: T) => T)) => void];

  export function useEffect(
    effect: () => void | (() => void),
    deps?: readonly unknown[]
  ): void;

  export function useRef<T>(initialValue: T): { current: T };
  export function useRef<T>(initialValue: T | null): { current: T | null };
  export function useRef<T = undefined>(): { current: T | undefined };

  export function useMemo<T>(
    factory: () => T,
    deps: readonly unknown[] | undefined
  ): T;

  export function useCallback<T extends (...args: any[]) => any>(
    callback: T,
    deps: readonly unknown[]
  ): T;

  export function createContext<T>(defaultValue: T): any;
  export function useContext<T>(context: any): T;

  export const StrictMode: any;
  export const Fragment: any;

  export type FC<P = {}> = (props: P) => ReactElement<any, any> | null;
  export type PropsWithChildren<P = {}> = P & { children?: ReactNode };

  export type FormEvent<T = any> = any;
  export type ChangeEvent<T = any> = any;
  export type MouseEvent<T = any> = any;
  export type DragEvent<T = any> = any;

  const React: any;
  export default React;
}

declare module "react-dom/client" {
  export function createRoot(container: Element | DocumentFragment): {
    render(children: any): void;
    unmount(): void;
  };
}

declare module "react-router-dom" {
  export function BrowserRouter(props: any): any;
  export function Routes(props: any): any;
  export function Route(props: any): any;
  export function useNavigate(): (path: string, options?: any) => void;
  export function useParams<T extends Record<string, string | undefined>>(): T;
  export function useLocation(): any;
  export function Link(props: any): any;
  export function NavLink(props: any): any;
  export function Outlet(): any;
}

declare module "clsx" {
  export type ClassValue = any;
  export function clsx(...inputs: any[]): string;
}

declare module "tailwind-merge" {
  export function twMerge(...inputs: any[]): string;
}

declare module "lucide-react" {
  export const Check: any;
  export const Activity: any;
  export const ArrowLeft: any;
  export const AlertCircle: any;
  export const AlertTriangle: any;
  export const CheckCircle: any;
  export const CheckCircle2: any;
  export const ChevronRight: any;
  export const ChevronDown: any;
  export const Clock: any;
  export const ExternalLink: any;
  export const FileText: any;
  export const FlaskConical: any;
  export const HelpCircle: any;
  export const Loader2: any;
  export const RefreshCw: any;
  export const Search: any;
  export const ShieldAlert: any;
  export const Terminal: any;
  export const Upload: any;
  export const UploadCloud: any;
  export const X: any;
  export const Play: any;
  export const ArrowRight: any;
  export const Sparkles: any;
  export const BarChart3: any;
  export const TrendingUp: any;
  export const DollarSign: any;
  export const Users: any;
  export const Target: any;
  export const Compass: any;
  export const Shield: any;
  export const ShieldCheck: any;
  export const Zap: any;
  export const KeyRound: any;
  export const Eye: any;
  export const EyeOff: any;
  export const Cpu: any;
  export const Layers: any;
  export const Bot: any;
  export const ThumbsUp: any;
  export const ThumbsDown: any;
  export const MessageSquare: any;
  export const CornerDownRight: any;
  export const RotateCcw: any;
  export const Award: any;
  export const Flame: any;
  export const Filter: any;
  export const Link2: any;
  export const Copy: any;
  export const Info: any;
  export const Send: any;
  export const Trash2: any;
  export const ArrowDownCircle: any;
  export const CheckSquare: any;
  export const Square: any;
  export const ChevronUp: any;
  export const Sliders: any;
  export const SlidersHorizontal: any;
  export const CirclePlus: any;
  export const PlusCircle: any;
  export const Plus: any;
  export const Radio: any;
  export const Megaphone: any;
  export const LayoutDashboard: any;
  export const Calendar: any;
  export const ChevronLeft: any;
  export const BookOpen: any;
  export const Bookmark: any;
  export const CreditCard: any;
  export const FolderOpen: any;
  export const Settings: any;
  export const LogOut: any;
  export const BarChart2: any;
  export const Stethoscope: any;
  export const Video: any;
  export const FileSpreadsheet: any;
  export const FileDown: any;
  export const Download: any;
  export const Printer: any;
  export const Users2: any;
  export const Bell: any;
  export const User: any;
  const icons: Record<string, any>;
  export default icons;
}


