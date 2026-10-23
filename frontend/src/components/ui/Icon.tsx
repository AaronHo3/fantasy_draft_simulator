import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  BarChart3,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleHelp,
  ClipboardList,
  Database,
  Download,
  Eye,
  EyeOff,
  Filter,
  Flag,
  History,
  Info,
  Link2,
  ListOrdered,
  Minus,
  Pencil,
  Play,
  RefreshCw,
  Search,
  Settings,
  Swords,
  Trophy,
  Undo2,
  Users,
  X,
  type LucideProps,
} from 'lucide-react'

const ICONS = {
  activity: Activity,
  warning: AlertTriangle,
  'arrow-down': ArrowDown,
  'arrow-up': ArrowUp,
  swap: ArrowLeftRight,
  chart: BarChart3,
  check: Check,
  'chevron-down': ChevronDown,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'chevron-up': ChevronUp,
  help: CircleHelp,
  clipboard: ClipboardList,
  database: Database,
  download: Download,
  eye: Eye,
  'eye-off': EyeOff,
  filter: Filter,
  flag: Flag,
  history: History,
  info: Info,
  link: Link2,
  list: ListOrdered,
  minus: Minus,
  edit: Pencil,
  play: Play,
  refresh: RefreshCw,
  search: Search,
  settings: Settings,
  matchup: Swords,
  trophy: Trophy,
  undo: Undo2,
  users: Users,
  close: X,
} as const

export type IconName = keyof typeof ICONS

interface IconProps extends Omit<LucideProps, 'ref'> {
  name: IconName
}

/** One icon set for the whole app (lucide), decorative by default. */
export function Icon({ name, size = 16, ...rest }: IconProps) {
  const Cmp = ICONS[name]
  return <Cmp size={size} strokeWidth={1.75} aria-hidden="true" focusable="false" {...rest} />
}
