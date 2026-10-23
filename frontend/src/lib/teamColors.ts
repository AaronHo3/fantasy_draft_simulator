// NBA team accent colors (primary brand color) keyed by tricode, used for portrait frames and leader accents.
export interface TeamColor {
  name: string
  primary: string
  secondary: string
}

export const TEAM_COLORS: Record<string, TeamColor> = {
  ATL: { name: 'Hawks', primary: '#C8102E', secondary: '#FDB927' },
  BOS: { name: 'Celtics', primary: '#007A33', secondary: '#BA9653' },
  BKN: { name: 'Nets', primary: '#000000', secondary: '#FFFFFF' },
  CHA: { name: 'Hornets', primary: '#1D1160', secondary: '#00788C' },
  CHI: { name: 'Bulls', primary: '#CE1141', secondary: '#000000' },
  CLE: { name: 'Cavaliers', primary: '#860038', secondary: '#FDBB30' },
  DAL: { name: 'Mavericks', primary: '#00538C', secondary: '#002B5E' },
  DEN: { name: 'Nuggets', primary: '#0E2240', secondary: '#FEC524' },
  DET: { name: 'Pistons', primary: '#C8102E', secondary: '#1D42BA' },
  GSW: { name: 'Warriors', primary: '#1D428A', secondary: '#FFC72C' },
  HOU: { name: 'Rockets', primary: '#CE1141', secondary: '#000000' },
  IND: { name: 'Pacers', primary: '#002D62', secondary: '#FDBB30' },
  LAC: { name: 'Clippers', primary: '#C8102E', secondary: '#1D428A' },
  LAL: { name: 'Lakers', primary: '#552583', secondary: '#FDB927' },
  MEM: { name: 'Grizzlies', primary: '#5D76A9', secondary: '#12173F' },
  MIA: { name: 'Heat', primary: '#98002E', secondary: '#F9A01B' },
  MIL: { name: 'Bucks', primary: '#00471B', secondary: '#EEE1C6' },
  MIN: { name: 'Timberwolves', primary: '#0C2340', secondary: '#236192' },
  NOP: { name: 'Pelicans', primary: '#0C2340', secondary: '#C8102E' },
  NYK: { name: 'Knicks', primary: '#006BB6', secondary: '#F58426' },
  OKC: { name: 'Thunder', primary: '#007AC1', secondary: '#EF6124' },
  ORL: { name: 'Magic', primary: '#0077C0', secondary: '#C4CED4' },
  PHI: { name: '76ers', primary: '#006BB6', secondary: '#ED174C' },
  PHX: { name: 'Suns', primary: '#1D1160', secondary: '#E56020' },
  POR: { name: 'Trail Blazers', primary: '#E03A3E', secondary: '#000000' },
  SAC: { name: 'Kings', primary: '#5A2D81', secondary: '#63727A' },
  SAS: { name: 'Spurs', primary: '#C4CED4', secondary: '#000000' },
  TOR: { name: 'Raptors', primary: '#CE1141', secondary: '#000000' },
  UTA: { name: 'Jazz', primary: '#002B5C', secondary: '#F9A01B' },
  WAS: { name: 'Wizards', primary: '#002B5C', secondary: '#E31837' },
}

export function teamColor(tricode: string | null | undefined): TeamColor {
  return (tricode && TEAM_COLORS[tricode]) || { name: tricode ?? 'Free agent', primary: '#4b555b', secondary: '#aeb6b1' }
}
