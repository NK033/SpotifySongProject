import React from 'react';

function Sidebar({
  isOpen,
  onClose,
  userInfo, // This might be null initially!
  onLogin,
  onLogout,
  pinnedPlaylists,
  onSelectPinned,
  onDeletePinned,
  onUpdatePinned,
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
            {/* ✅ FIX 1: Only show Avatar and Name if userInfo exists */}
            {userInfo ? (
              <>
                <img src={userInfo.avatar} alt="User Avatar" className="w-16 h-16 rounded-full mb-2" />
                <span className="text-lg font-medium text-[var(--text-primary)] break-words w-full text-center">
                  {userInfo.displayName}
                </span>
              </>
            ) : (
              // Optional: Show a guest icon if no user info
              <div className="w-16 h-16 rounded-full mb-2 bg-gray-600 flex items-center justify-center">
                <i className="fas fa-user text-gray-300 text-2xl"></i>
              </div>
            )}

            {/* ✅ FIX 2: Use optional chaining (?.) to safely check isLoggedIn */}
            {!userInfo?.isLoggedIn ? (
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
              {/* ✅ FIX 3: Add a safe check for pinnedPlaylists in case it is undefined */}
              {pinnedPlaylists && pinnedPlaylists.map((item) => (
                <div 
                  key={item.pin_id}
                  className="w-full flex items-center justify-between text-left text-sm p-2 rounded-lg hover:bg-[var(--bg-glass)] hover:border-[var(--border-color)] border border-transparent transition-colors text-gray-300 group"
                >
                  <button 
                    onClick={() => onSelectPinned(item.pin_id)}
                    className="flex-grow text-left overflow-hidden"
                  >
                    <div className="font-medium truncate text-[var(--text-primary)]">{item.name}</div>
                    <div className="text-xs text-[var(--text-secondary)]">
                      {new Date(item.timestamp).toLocaleDateString('th-TH')}
                    </div>
                  </button>
                  
                  <button 
                    onClick={(e) => { e.stopPropagation(); onUpdatePinned(item); }}
                    className="flex-shrink-0 p-2 ml-1 rounded-full text-gray-500 hover:text-blue-400 hover:bg-[var(--bg-glass)] transition-all opacity-0 group-hover:opacity-100"
                    title="เปลี่ยนชื่อ"
                  >
                    <i className="fas fa-pencil-alt fa-xs"></i>
                  </button>

                  <button 
                    onClick={(e) => { e.stopPropagation(); onDeletePinned(item.pin_id, item.name); }}
                    className="flex-shrink-0 p-2 ml-1 rounded-full text-gray-500 hover:text-red-500 hover:bg-[var(--bg-glass)] transition-all opacity-0 group-hover:opacity-100"
                    title="ลบ"
                  >
                    <i className="fas fa-trash-alt fa-xs"></i>
                  </button>
                </div>
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