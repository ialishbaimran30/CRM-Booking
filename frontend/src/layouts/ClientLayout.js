import React from 'react';
import { Outlet } from 'react-router-dom';
import ClientSidebar from '../components/ClientSidebar';

export default function ClientLayout() {
  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <ClientSidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}