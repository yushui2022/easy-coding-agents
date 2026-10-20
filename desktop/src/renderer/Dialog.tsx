import React, {useEffect, useRef} from 'react';
import {X} from '@phosphor-icons/react';

// Native dialogs trap focus, make the workspace inert and restore the opener on close.
export function Dialog({title, name, closeLabel, onClose, wide, className = '', children}: {
  title: string; name?: string; closeLabel: string; onClose: () => void;
  wide?: boolean; className?: string; children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const opener = document.activeElement as HTMLElement | null;
    dialog.showModal();
    return () => {
      dialog.close();
      // React may detach the dialog before passive effect cleanup; restore after unmount.
      queueMicrotask(() => {if (opener?.isConnected) opener.focus();});
    };
  }, []);
  return <dialog className={`eca-dialog ${wide ? 'wide' : ''} ${className}`} aria-label={name || title} ref={ref}
    onCancel={event => {event.preventDefault(); onClose();}}>
    <header><h2>{title}</h2><button className="icon-button" aria-label={closeLabel} onClick={onClose}><X size={19}/></button></header>
    <div className="dialog-body">{children}</div>
  </dialog>;
}
