/** Material Symbols Outlined icon (https://fonts.google.com/icons). */
export default function Icon({name, className = "", size}) {
  const style = size ? {fontSize: typeof size === "number" ? `${size}px` : size} : undefined;
  return <span className={`material-symbols-outlined icon${className ? ` ${className}` : ""}`}
               style={style} aria-hidden="true">{name}</span>;
}
