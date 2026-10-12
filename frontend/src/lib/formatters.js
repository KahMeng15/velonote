export const formatParams = (mode, format, method) => {
  const parts = [mode, format, method].filter(Boolean).map(s => 
    s.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
  );
  if (parts.length === 3) return `${parts[0]} in ${parts[1]} (${parts[2]})`;
  if (parts.length === 2) return `${parts[0]} in ${parts[1]}`;
  if (parts.length === 1) return parts[0];
  return '';
};
