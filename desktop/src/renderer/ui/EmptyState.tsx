import React from 'react';

/** Shared presentation only; the owning panel decides content and actions. */
export function EmptyState({icon, title, children}: {
  icon: React.ReactNode; title: string; children: React.ReactNode;
}) {
  return <div className="empty-state">
    <span className="empty-state-icon" aria-hidden="true">{icon}</span>
    <strong>{title}</strong>
    <div className="empty-state-description">{children}</div>
  </div>;
}
