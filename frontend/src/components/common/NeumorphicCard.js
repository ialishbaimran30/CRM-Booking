import React from 'react';
import clsx from 'clsx';

export const NeumorphicCard = ({ children, className, onClick }) => {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'bg-[#F4F7FC] rounded-2xl p-6 transition-all duration-200',
        'shadow-[8px_8px_16px_#d0d9e8,-8px_-8px_16px_#ffffff]',
        onClick && 'cursor-pointer hover:shadow-[4px_4px_8px_#d0d9e8,-4px_-4px_8px_#ffffff]',
        className
      )}
    >
      {children}
    </div>
  );
};