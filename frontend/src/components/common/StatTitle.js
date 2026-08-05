import React from 'react';

export default function StatTile({ label, value, icon, colorClass = "text-blue-600" }) {
  return (
    <div className="neu-card p-5 flex items-center justify-between border border-white/60">
      <div>
        <p className="text-xs uppercase font-semibold text-gray-500 tracking-wider">{label}</p>
        <p className={`text-3xl font-bold mt-1.5 ${colorClass}`}>{value}</p>
      </div>
      <div className="w-12 h-12 rounded-2xl bg-[#F4F7FC] shadow-[4px_4px_10px_#D2D9E6,-4px_-4px_10px_#FFFFFF] flex items-center justify-center text-xl">
        {icon}
      </div>
    </div>
  );
}