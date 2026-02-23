// src/components/Sidebar.jsx
import React from 'react';
// ✅ Import useAppContext เพื่อดึงฟังก์ชันลบแชท
import { useAppContext } from '../contexts/AppContext'; 

function Sidebar({
  isOpen,
  onClose,
  userInfo, 
  onLogin,
  onLogout,
  pinnedPlaylists,
  onSelectPinned,
  onDeletePinned,
  onUpdatePinned,
  currentTheme,
  onToggleTheme
}) {
  
  // ✅ ดึง handleClearChat มาใช้ (และ handleOpenFeedbackModal ตัวเดิม)
  const { handleOpenFeedbackModal, handleClearChat } = useAppContext(); 

  const userImage = userInfo?.images?.[0]?.url || userInfo?.avatar || "https://cdn-icons-png.flaticon.com/512/847/847969.png";
  const userName = userInfo?.display_name || userInfo?.displayName || "ผู้ใช้งาน";

  return (
    <>
      <div
        className={`fixed inset-0 bg-black opacity-50 z-40 md:hidden ${isOpen ? '' : 'hidden'}`}
        onClick={onClose}
      ></div>

      <div className={`fixed z-50 top-0 left-0 h-full w-64 bg-[var(--bg-secondary)] transform transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex flex-col h-full p-4">
          
          {/* ส่วนหัว Sidebar (คงเดิม) */}
          <div className="flex items-center justify-between pb-4 border-b border-[var(--border-color)]">
             <div className="flex items-center space-x-2">
              <i className="fas fa-robot text-green-500"></i>
              <h2 className="text-[var(--text-primary)] text-lg font-semibold">AI Playlist</h2>
            </div>
            <button onClick={onClose} className="md:hidden text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
              <i className="fas fa-times"></i>
            </button>
          </div>

          {/* ส่วน User Profile (คงเดิม) */}
          <div className="mt-4 flex flex-col items-center">
             {userInfo ? (
              <>
                <img src={userImage} alt="User" className="w-16 h-16 rounded-full mb-2 object-cover border-2 border-green-500" onError={(e) => { e.target.src = "https://cdn-icons-png.flaticon.com/512/847/847969.png"; }} />
                <span className="text-lg font-medium text-[var(--text-primary)] break-words w-full text-center">{userName}</span>
              </>
            ) : (
                <div className="w-16 h-16 rounded-full mb-2 bg-[var(--bg-glass)] flex items-center justify-center border border-[var(--border-color)]">
                  <i className="fas fa-user text-[var(--text-muted)] text-2xl"></i>
                </div>
            )}
             
             {!userInfo ? (
              <button onClick={onLogin} className="mt-4 w-full py-2 px-4 rounded-full font-medium transition-colors bg-green-500 text-white hover:bg-green-600">
                <i className="fab fa-spotify mr-2"></i> เข้าสู่ระบบด้วย Spotify
              </button>
            ) : (
              <button onClick={onLogout} className="mt-2 w-full py-2 px-4 rounded-full font-medium transition-colors bg-red-500 text-white hover:bg-red-600">
                <i className="fas fa-sign-out-alt mr-2"></i> ออกจากระบบ Spotify
              </button>
            )}
          </div>

          {/* ส่วนรายการเมนูและ Pin Playlist */}
           <div className="flex-grow p-2 overflow-y-auto mt-4 border-t border-[var(--border-color)]">
                
                {/* ปุ่มประวัติ Like/Dislike (คงเดิม) */}
                {userInfo && (
                    <button 
                        onClick={handleOpenFeedbackModal}
                        className="w-full flex items-center space-x-3 p-3 mb-2 rounded-xl bg-[var(--bg-glass)] hover:bg-[var(--bg-hover)] transition-all text-[var(--text-primary)] border border-transparent hover:border-[var(--border-color)] shadow-sm group"
                    >
                        <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 group-hover:bg-blue-500 group-hover:text-white transition-colors">
                            <i className="fas fa-history"></i>
                        </div>
                        <div className="text-left">
                            <div className="font-medium text-sm">ประวัติ Like/Dislike</div>
                            <div className="text-xs text-[var(--text-secondary)]">จัดการเพลงที่เคยให้เรตติ้ง</div>
                        </div>
                    </button>
                )}

                {/* ✅ เพิ่มปุ่ม: ล้างประวัติแชท (แทรกตรงนี้) */}
                <button 
                    onClick={handleClearChat}
                    className="w-full flex items-center space-x-3 p-3 mb-4 rounded-xl bg-[var(--bg-glass)] hover:bg-red-500/10 hover:border-red-500/30 transition-all text-[var(--text-primary)] border border-transparent hover:border-red-500/30 shadow-sm group"
                >
                    <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center text-red-400 group-hover:bg-red-500 group-hover:text-white transition-colors">
                        <i className="fas fa-trash-alt"></i>
                    </div>
                    <div className="text-left">
                        <div className="font-medium text-sm group-hover:text-red-400">ล้างประวัติแชท</div>
                        <div className="text-xs text-[var(--text-secondary)]">เริ่มบทสนทนาใหม่</div>
                    </div>
                </button>

                <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2 px-2 pt-2">ประวัติเพลย์ลิสต์ที่ Pin ไว้</h3>
                
                {/* Loop แสดงรายการ Pin (คงเดิม) */}
                <div className="space-y-1">
                  {pinnedPlaylists && pinnedPlaylists.map((item) => (
                    <div key={item.pin_id} className="w-full flex items-center justify-between text-left text-sm p-2 rounded-lg hover:bg-[var(--bg-glass)] hover:border-[var(--border-color)] border border-transparent transition-colors text-[var(--text-secondary)] group">
                      <button onClick={() => onSelectPinned(item)} className="flex-grow text-left overflow-hidden">
                        <div className="font-medium truncate text-[var(--text-primary)]">{item.name}</div>
                        <div className="text-xs text-[var(--text-secondary)]">{new Date(item.timestamp).toLocaleDateString('th-TH')}</div>
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); onUpdatePinned(item); }} className="flex-shrink-0 p-2 ml-1 rounded-full text-[var(--text-muted)] hover:text-blue-500 hover:bg-[var(--bg-glass)] transition-all opacity-0 group-hover:opacity-100" title="เปลี่ยนชื่อ"><i className="fas fa-pencil-alt fa-xs"></i></button>
                      <button onClick={(e) => { e.stopPropagation(); onDeletePinned(item.pin_id, item.name); }} className="flex-shrink-0 p-2 ml-1 rounded-full text-[var(--text-muted)] hover:text-red-500 hover:bg-[var(--bg-glass)] transition-all opacity-0 group-hover:opacity-100" title="ลบ"><i className="fas fa-trash-alt fa-xs"></i></button>
                    </div>
                  ))}
                </div>
           </div>

          {/* ส่วนสลับ Theme (คงเดิม) */}
          <div className="mt-auto pt-4 border-t border-[var(--border-color)]">
            <button
              onClick={onToggleTheme}
              className="w-full flex items-center justify-between py-2 px-4 rounded-lg text-[var(--text-primary)] hover:bg-[var(--bg-glass)] transition-colors"
            >
              <span>
                {currentTheme === 'dark' ? <><i className="fas fa-sun mr-2 text-yellow-400"></i> โหมดกลางวัน</> : <><i className="fas fa-moon mr-2 text-blue-400"></i> โหมดกลางคืน</>}
              </span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;