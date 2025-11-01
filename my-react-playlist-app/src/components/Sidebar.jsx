import React from 'react';

function Sidebar({
  isOpen,
  onClose,
  userInfo,
  onLogin,
  onLogout,
  pinnedPlaylists,
  onSelectPinned,
  currentTheme,
  onToggleTheme
}) {
  return (
    <>
      <div
        className={`fixed inset-0 bg-black opacity-50 z-40 md:hidden ${isOpen ? '' : 'hidden'}`}
        onClick={onClose}
      ></div>

      <div className={`fixed z-50 top-0 left-0 h-full w-64 bg-[var(--bg-secondary)] transform transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex flex-col h-full p-4">
          <div className="flex items-center justify-between pb-4 border-b border-[var(--border-color)]">
            <div className="flex items-center space-x-2">
              <i className="fas fa-robot text-green-400"></i>
              <h2 className="text-[var(--text-primary)] text-lg font-semibold">AI Playlist</h2>
            </div>
            <button onClick={onClose} className="md:hidden text-gray-400 hover:text-white transition-colors">
              <i className="fas fa-times"></i>
            </button>
          </div>
          <div className="mt-4 flex flex-col items-center">
            <img src={userInfo.avatar} alt="User Avatar" className="w-16 h-16 rounded-full mb-2" />
            <span className="text-lg font-medium text-[var(--text-primary)] break-words w-full text-center">{userInfo.displayName}</span>
            {!userInfo.isLoggedIn ? (
              <button onClick={onLogin} className="mt-4 w-full py-2 px-4 rounded-full font-medium transition-colors bg-green-500 text-white hover:bg-green-600">
                <i className="fab fa-spotify mr-2"></i> เข้าสู่ระบบด้วย Spotify
              </button>
            ) : (
              <button onClick={onLogout} className="mt-2 w-full py-2 px-4 rounded-full font-medium transition-colors bg-red-500 text-white hover:bg-red-600">
                <i className="fas fa-sign-out-alt mr-2"></i> ออกจากระบบ Spotify
              </button>
            )}
          </div>
          <div className="flex-grow p-2 overflow-y-auto mt-4 border-t border-[var(--border-color)]">
            <h3 className="text-sm font-semibold text-gray-400 mb-2 px-2 pt-2">ประวัติเพลย์ลิสต์ที่ Pin ไว้</h3>
            <div className="space-y-1">
              {pinnedPlaylists.map((item, index) => (
                <button key={index} onClick={() => onSelectPinned(index)} className="w-full text-left text-sm p-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-300">
                  <div className="font-medium">{item.name}</div>
                  <div className="text-xs text-gray-400">Pinned on: {new Date(item.timestamp).toLocaleDateString('th-TH')}</div>
                </button>
              ))}
            </div>
          </div>
          <div className="mt-auto pt-4 border-t border-[var(--border-color)]">
            <button
              onClick={onToggleTheme}
              className="w-full flex items-center justify-between py-2 px-4 rounded-lg text-gray-300 hover:bg-opacity-50 hover:bg-gray-500 transition-colors"
            >
              <span>
                {currentTheme === 'dark' ? <><i className="fas fa-sun mr-2"></i> โหมดกลางวัน</> : <><i className="fas fa-moon mr-2"></i> โหมดกลางคืน</>}
              </span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;