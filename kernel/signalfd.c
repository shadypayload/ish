// signalfd: a file descriptor that reads the caller's pending signals from a
// given set, for programs that take signals in their event loop (the set is
// blocked first, so the signals stay pending instead of running a handler).
#include <string.h>
#include "kernel/calls.h"
#include "kernel/task.h"
#include "kernel/signal.h"
#include "kernel/fs.h"
#include "fs/fd.h"
#include "fs/poll.h"

static struct fd_ops signalfd_ops;
static lock_t signalfds_lock = LOCK_INITIALIZER;
static struct list signalfds = {&signalfds, &signalfds};

// what read() returns for each signal (Linux's struct signalfd_siginfo)
struct signalfd_siginfo_ {
    uint32_t signo;
    int32_t err;
    int32_t code;
    uint32_t pid;
    uint32_t uid;
    int32_t fd;
    uint32_t tid;
    uint32_t band;
    uint32_t overrun;
    uint32_t trapno;
    int32_t status;
    int32_t int_;
    uint64_t ptr;
    uint64_t utime;
    uint64_t stime;
    uint64_t addr;
    uint16_t addr_lsb;
    uint8_t pad[46];
};
_Static_assert(sizeof(struct signalfd_siginfo_) == 128, "signalfd_siginfo size");

// SIGKILL and SIGSTOP cannot be taken this way; Linux drops them from the set
static sigset_t_ signalfd_usable(sigset_t_ mask) {
    sigset_del(&mask, SIGKILL_);
    sigset_del(&mask, SIGSTOP_);
    return mask;
}

int_t sys_signalfd4(fd_t f, addr_t mask_addr, uint_t mask_size, int_t flags) {
    STRACE("signalfd4(%d, %#x, %d, %#x)", f, mask_addr, mask_size, flags);
    if (flags & ~(O_CLOEXEC_|O_NONBLOCK_))
        return _EINVAL;
    if (mask_size != sizeof(sigset_t_))
        return _EINVAL;
    sigset_t_ mask;
    if (user_get(mask_addr, mask))
        return _EFAULT;
    mask = signalfd_usable(mask);

    if (f != -1) {
        // change the set of an existing signalfd
        struct fd *fd = f_get(f);
        if (fd == NULL)
            return _EBADF;
        if (fd->ops != &signalfd_ops)
            return _EINVAL;
        lock(&signalfds_lock);
        fd->signalfd.mask = mask;
        unlock(&signalfds_lock);
        poll_wakeup(fd, POLL_READ);
        return f;
    }

    struct fd *fd = adhoc_fd_create(&signalfd_ops);
    if (fd == NULL)
        return _ENOMEM;
    fd->signalfd.mask = mask;
    lock(&signalfds_lock);
    list_add(&signalfds, &fd->signalfd.others);
    unlock(&signalfds_lock);
    return f_install(fd, flags);
}
int_t sys_signalfd(fd_t f, addr_t mask_addr, uint_t mask_size) {
    return sys_signalfd4(f, mask_addr, mask_size, 0);
}

// A signal was queued for some task: anything polling a signalfd that takes
// this signal has to look again. Called without the sighand lock.
void signalfd_notify(int sig) {
    lock(&signalfds_lock);
    struct fd *fd;
    list_for_each_entry(&signalfds, fd, signalfd.others) {
        if (sigset_has(fd->signalfd.mask, sig))
            poll_wakeup(fd, POLL_READ);
    }
    unlock(&signalfds_lock);
}

static void signalfd_fill(struct signalfd_siginfo_ *out, const struct siginfo_ *info) {
    memset(out, 0, sizeof(*out));
    out->signo = info->sig;
    out->err = info->sig_errno;
    out->code = info->code;
    if (info->sig == SIGCHLD_) {
        out->pid = info->child.pid;
        out->uid = info->child.uid;
        out->status = info->child.status;
        out->utime = info->child.utime;
        out->stime = info->child.stime;
    } else if (info->code == SI_TIMER_) {
        out->tid = info->timer.timer;
        out->overrun = info->timer.overrun;
        out->int_ = info->timer.value.sv_int;
        out->ptr = info->timer.value.sv_ptr;
    } else if (info->code <= 0) {
        // sent by a process (kill, tgkill, sigqueue)
        out->pid = info->kill.pid;
        out->uid = info->kill.uid;
    }
}

static ssize_t signalfd_read(struct fd *fd, void *buf, size_t bufsize) {
    if (bufsize < sizeof(struct signalfd_siginfo_))
        return _EINVAL;
    size_t max = bufsize / sizeof(struct signalfd_siginfo_);
    struct signalfd_siginfo_ *out = buf;
    size_t count = 0;

    lock(&current->sighand->lock);
    while (true) {
        sigset_t_ mask = fd->signalfd.mask;
        struct sigqueue *sigqueue, *tmp;
        list_for_each_entry_safe(&current->queue, sigqueue, tmp, queue) {
            if (count >= max)
                break;
            if (!sigset_has(mask, sigqueue->info.sig))
                continue;
            list_remove(&sigqueue->queue);
            sigset_del(&current->pending, sigqueue->info.sig);
            signalfd_fill(&out[count++], &sigqueue->info);
            free(sigqueue);
        }
        if (count > 0)
            break;
        if (fd->flags & O_NONBLOCK_) {
            unlock(&current->sighand->lock);
            return _EAGAIN;
        }
        // wait the way sigtimedwait does: a signal from the set wakes this
        // task even though it is blocked
        assert(current->waiting == 0);
        current->waiting = mask;
        int err = wait_for(&current->pause, &current->sighand->lock, NULL);
        current->waiting = 0;
        if (err < 0) {
            // woken by a signal: take it if it is ours, otherwise the call
            // is interrupted
            bool ours = false;
            list_for_each_entry(&current->queue, sigqueue, queue) {
                if (sigset_has(mask, sigqueue->info.sig)) {
                    ours = true;
                    break;
                }
            }
            if (!ours) {
                unlock(&current->sighand->lock);
                return _EINTR;
            }
        }
    }
    unlock(&current->sighand->lock);
    return count * sizeof(struct signalfd_siginfo_);
}

// No lock: called with poll locks held, in the polling task. A stale answer
// is corrected by the wakeup that follows every queued signal.
static int signalfd_poll(struct fd *fd) {
    return (current->pending & fd->signalfd.mask) ? POLL_READ : 0;
}

static int signalfd_close(struct fd *fd) {
    lock(&signalfds_lock);
    list_remove(&fd->signalfd.others);
    unlock(&signalfds_lock);
    return 0;
}

static struct fd_ops signalfd_ops = {
    .read = signalfd_read,
    .poll = signalfd_poll,
    .close = signalfd_close,
};
