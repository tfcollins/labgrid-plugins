interface ChipIconProps {
  size?: number;
}

export default function ChipIcon({ size = 36 }: ChipIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 170 155" xmlns="http://www.w3.org/2000/svg" style={{ display: "block" }}>
      <rect x="40" y="30" width="90" height="90" stroke="#e6edf3" fill="none" strokeWidth="4" strokeLinecap="square" />
      <line x1="60" y1="30" x2="60" y2="10" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="54" y="2" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="110" y1="30" x2="110" y2="10" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="104" y="2" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="60" y1="120" x2="60" y2="140" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="54" y="140" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="110" y1="120" x2="110" y2="140" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="104" y="140" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="40" y1="55" x2="20" y2="55" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="8" y="49" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="40" y1="95" x2="20" y2="95" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="8" y="89" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="130" y1="55" x2="150" y2="55" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="150" y="49" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <line x1="130" y1="95" x2="150" y2="95" stroke="#e6edf3" strokeWidth="4" strokeLinecap="square" />
      <rect x="150" y="89" width="12" height="12" stroke="#e6edf3" fill="none" strokeWidth="4" />
      <polyline points="50,75 70,75 80,60 95,95 110,75 120,75" stroke="#4db8ff" fill="none" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
