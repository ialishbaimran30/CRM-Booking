import React from 'react';
import clsx from 'clsx';

const statusStyles = {
  active: 'bg-[#3FBF8F]/15 text-[#3FBF8F]',
  inactive: 'bg-[#6B7A90]/15 text-[#6B7A90]',
  pending: 'bg-[#F2A93C]/15 text-[#F2A93C]',
  confirmed: 'bg-[#3E7BFA]/15 text-[#3E7BFA]',
  completed: 'bg-[#3FBF8F]/15 text-[#3FBF8F]',
  cancelled: 'bg-[#F0563F]/15 text-[#F0563F]',
  paid: 'bg-[#3FBF8F]/15 text-[#3FBF8F]',
  refunded: 'bg-[#F2A93C]/15 text-[#F2A93C]',
};

export const StatusBadge = ({ status }) => {
  const normalized = status?.toLowerCase() || 'pending';
  return (
    <span
      className={clsx(
        'px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider',
        statusStyles[normalized] || 'bg-gray-200 text-gray-700'
      )}
    >
      {status}
    </span>
  );
};