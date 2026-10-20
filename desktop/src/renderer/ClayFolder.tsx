/** Decorative project icon; the adjacent label supplies its accessible name. */
export function ClayFolder({size=24,className=''}:{size?:number;className?:string}) {
  return <img className={`clay-folder ${className}`} src="./clay-folder.png" width={size} height={size} alt="" decoding="async" draggable={false}/>;
}
