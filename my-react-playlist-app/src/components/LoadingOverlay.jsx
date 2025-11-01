import React from 'react';

function LoadingOverlay() {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]">
      <div className="flex flex-col items-center p-6 rounded-lg bg-gray-800 text-white shadow-lg">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-green-500 border-t-transparent"></div>
        <p className="mt-4 text-sm font-medium">กำลังโหลด...</p>
      </div>
    </div>
  );
}

export default LoadingOverlay;