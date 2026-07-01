"""
Fall Detection Alert System - Simple & Safe Version
==================================================

Fixed issues:
- No infinite loops
- Simpler structure
- Clear retry limits
- Better error handling
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from panoramisk.manager import Manager

# === Simple Configuration ===
@dataclass
class AlertConfig:
    """Simple configuration - easy to modify"""
    # AMI Connection
    ami_host: str = '127.0.0.1'
    ami_port: int = 5038
    ami_username: str = 'hx'
    ami_secret: str = '123'
    
    # Alert Settings
    extensions: List[str] = None
    alert_message: str = "⚠️ EMERGENCY: Fall detected! Please check immediately."
    caller_id: str = "FallAlert"
    context: str = 'internal'
    from_endpoint: str = 'pjsip:server'
    
    # Safety Settings
    max_retries: int = 1  # Limited retries to prevent loops
    connection_timeout: int = 10
    response_wait_time: int = 3
    
    def __post_init__(self):
        if self.extensions is None:
            self.extensions = ['6001', '6002', '6003']

class FallAlertSystem:
    """Simple, safe alert system"""
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self.setup_logging()
        self.manager = None
        self.stats = {
            'calls_sent': 0,
            'calls_success': 0,
            'sms_sent': 0,
            'sms_success': 0,
            'start_time': datetime.now()
        }
    
    def setup_logging(self):
        """Setup simple logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    async def connect(self) -> bool:
        """Connect once, no infinite retries"""
        try:
            self.logger.info("🔌 Connecting to AMI...")
            self.manager = Manager(
                host=self.config.ami_host,
                port=self.config.ami_port,
                username=self.config.ami_username,
                secret=self.config.ami_secret
            )
            
            # Single connection attempt with timeout
            await asyncio.wait_for(
                self.manager.connect(), 
                timeout=self.config.connection_timeout
            )
            
            self.logger.info("✅ Connected successfully!")
            return True
            
        except asyncio.TimeoutError:
            self.logger.error("❌ Connection timeout")
            return False
        except Exception as e:
            self.logger.error(f"❌ Connection failed: {e}")
            return False
    
    async def make_call(self, extension: str) -> bool:
        """Make ONE call attempt (no infinite retries)"""
        self.stats['calls_sent'] += 1
        
        try:
            response = await self.manager.send_action({
                'Action': 'Originate',
                'Channel': f'PJSIP/{extension}',
                'Context': self.config.context,
                'Exten': extension,
                'Priority': 1,
                'CallerID': f'{self.config.caller_id} <{extension}>',
                'Async': 'true',
                'Timeout': '30000'
            })
            
            success = response.get('Response') == 'Success'
            if success:
                self.stats['calls_success'] += 1
            
            status = "✅" if success else "❌"
            message = response.get('Message', 'No message')
            self.logger.info(f"[📞] {extension} | {status} {message}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"[📞] {extension} | ❌ Error: {e}")
            return False
    
    async def send_sms(self, extension: str) -> bool:
        """Send ONE SMS attempt (no infinite retries)"""
        self.stats['sms_sent'] += 1
        
        try:
            response = await self.manager.send_action({
                'Action': 'MessageSend',
                'To': f'pjsip:{extension}',
                'From': self.config.from_endpoint,
                'Body': self.config.alert_message
            })
            
            success = response.get('Response') == 'Success'
            if success:
                self.stats['sms_success'] += 1
            
            status = "✅" if success else "❌"
            message = response.get('Message', 'No message')
            self.logger.info(f"[📨] {extension} | {status} {message}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"[📨] {extension} | ❌ Error: {e}")
            return False
    
    async def alert_extension(self, extension: str) -> Dict[str, Any]:
        """Alert one extension - call + SMS in parallel"""
        self.logger.info(f"[🚨] Alerting {extension}...")
        
        # Do both simultaneously
        call_result, sms_result = await asyncio.gather(
            self.make_call(extension),
            self.send_sms(extension),
            return_exceptions=True
        )
        
        # Handle exceptions
        call_success = call_result if isinstance(call_result, bool) else False
        sms_success = sms_result if isinstance(sms_result, bool) else False
        
        # Log result
        call_icon = "✅" if call_success else "❌"
        sms_icon = "✅" if sms_success else "❌"
        self.logger.info(f"[🎯] {extension} | Call: {call_icon} SMS: {sms_icon}")
        
        return {
            'extension': extension,
            'call_success': call_success,
            'sms_success': sms_success,
            'any_success': call_success or sms_success
        }
    
    def get_summary(self) -> str:
        """Simple statistics summary"""
        duration = (datetime.now() - self.stats['start_time']).total_seconds()
        return (
            f"📊 SUMMARY: "
            f"Calls: {self.stats['calls_success']}/{self.stats['calls_sent']} | "
            f"SMS: {self.stats['sms_success']}/{self.stats['sms_sent']} | "
            f"Time: {duration:.1f}s"
        )
    
    async def run(self, extensions: Optional[List[str]] = None) -> bool:
        """Main execution - simple and safe"""
        target_extensions = extensions or self.config.extensions
        
        self.logger.info("🚨 === FALL ALERT SYSTEM STARTING ===")
        self.logger.info(f"📋 Targets: {', '.join(target_extensions)}")
        
        try:
            # Step 1: Connect (no retries)
            if not await self.connect():
                self.logger.error("💥 Cannot connect - stopping")
                return False
            
            # Step 2: Send alerts (parallel, no retries)
            self.logger.info(f"🚀 Sending alerts to {len(target_extensions)} extensions...")
            
            results = await asyncio.gather(
                *[self.alert_extension(ext) for ext in target_extensions],
                return_exceptions=True
            )
            
            # Step 3: Process results
            successful = 0
            for result in results:
                if isinstance(result, dict) and result.get('any_success'):
                    successful += 1
            
            self.logger.info(f"🎯 Completed: {successful}/{len(target_extensions)} successful")
            
            # Step 4: Wait briefly for responses
            await asyncio.sleep(self.config.response_wait_time)
            
            return successful > 0
            
        except KeyboardInterrupt:
            self.logger.warning("⚠️ Interrupted by user")
            return False
        except Exception as e:
            self.logger.error(f"💥 System error: {e}")
            return False
        finally:
            # Always cleanup
            if self.manager:
                try:
                    self.manager.close()
                    self.logger.info("🔌 Connection closed")
                except:
                    pass  # Ignore cleanup errors
            
            self.logger.info(self.get_summary())
            self.logger.info("🚨 === SYSTEM FINISHED ===")

# === Easy Usage Functions ===

def create_system(extensions: List[str] = None, 
                 message: str = None,
                 username: str = 'hx') -> FallAlertSystem:
    """Create system with custom settings"""
    config = AlertConfig()
    
    if extensions:
        config.extensions = extensions
    if message:
        config.alert_message = message
    if username:
        config.ami_username = username
    
    return FallAlertSystem(config)

async def quick_alert(extensions: List[str], message: str = None):
    """Quick one-liner alert function"""
    system = create_system(extensions, message)
    return await system.run()

# === Main Functions ===

async def main():
    """Standard usage"""
    system = FallAlertSystem()
    await system.run()

async def custom_example():
    """Custom usage example"""
    system = create_system(
        extensions=['6001', '6002'],
        message="Custom emergency alert!",
        username='admin'
    )
    await system.run()

async def quick_example():
    """Quick usage example"""
    await quick_alert(['6001', '6003'], "Fall detected!")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
    except Exception as e:
        print(f"💥 Error: {e}")
